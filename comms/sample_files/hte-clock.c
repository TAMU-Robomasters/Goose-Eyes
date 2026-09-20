// SPDX-License-Identifier: GPL-2.0
/*
 * Simple Tegra HTE GPIO timestamp driver.
 *
 * Creates:
 *
 *   /dev/hte_clock0
 *
 * Device tree node should provide:
 *
 *   compatible = "custom,hte-clock";
 *   in-gpios = <&gpio_aon 9 0>;
 *   timestamps = <&hte_aon 9>;
 *   timestamp-names = "external-clock";
 *
 * This driver configures the GPIO IRQ as RISING EDGE and asks HTE
 * to timestamp using HTE_EDGE_NO_SETUP.
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/gpio/consumer.h>
#include <linux/interrupt.h>
#include <linux/hte.h>

#include <linux/miscdevice.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/kfifo.h>
#include <linux/wait.h>
#include <linux/poll.h>
#include <linux/spinlock.h>
#include <linux/atomic.h>
#include <linux/slab.h>

#define HTE_CLOCK_FIFO_DEPTH 1024

/*
 * Binary layout read by Python.
 *
 * Python struct format:
 *
 *   "<QQII"
 *
 * Fields:
 *
 *   __u64 timestamp_ns;
 *   __u64 sequence;
 *   __u32 gpio;
 *   __u32 edge;
 */
struct hte_clock_event {
    __u64 timestamp_ns;
    __u64 sequence;
    __u32 gpio;
    __u32 edge;
};

struct hte_clock_dev {
    struct device *dev;

    struct gpio_desc *in_gpio;
    int irq;

    struct hte_ts_desc desc;

    struct miscdevice miscdev;

    DECLARE_KFIFO_PTR(fifo, struct hte_clock_event);

    wait_queue_head_t readq;
    spinlock_t fifo_lock;

    atomic64_t dropped;
    bool hte_enabled;
};

static enum hte_return hte_clock_cb(struct hte_ts_data *ts, void *data)
{
    struct hte_clock_dev *priv = data;
    struct hte_clock_event ev;
    unsigned long flags;

    /*
     * The GPIO IRQ is configured rising-edge only, so this should
     * represent a rising-edge timestamp.
     */
    ev.timestamp_ns = ts->tsc;
    ev.sequence = ts->seq;
    ev.gpio = priv->desc.attr.line_id;
    ev.edge = 1;

    spin_lock_irqsave(&priv->fifo_lock, flags);

    if (kfifo_avail(&priv->fifo) > 0)
        kfifo_in(&priv->fifo, &ev, 1);
    else
        atomic64_inc(&priv->dropped);

    spin_unlock_irqrestore(&priv->fifo_lock, flags);

    wake_up_interruptible(&priv->readq);

    return HTE_CB_HANDLED;
}

static ssize_t hte_clock_read(struct file *file,
                  char __user *buf,
                  size_t len,
                  loff_t *ppos)
{
    struct hte_clock_dev *priv = file->private_data;
    struct hte_clock_event ev;
    unsigned long flags;
    int ret;

    if (len < sizeof(ev))
        return -EINVAL;

    if (kfifo_is_empty(&priv->fifo)) {
        if (file->f_flags & O_NONBLOCK)
            return -EAGAIN;

        ret = wait_event_interruptible(priv->readq,
                           !kfifo_is_empty(&priv->fifo));
        if (ret)
            return ret;
    }

    spin_lock_irqsave(&priv->fifo_lock, flags);
    ret = kfifo_out(&priv->fifo, &ev, 1);
    spin_unlock_irqrestore(&priv->fifo_lock, flags);

    if (ret != 1)
        return -EAGAIN;

    if (copy_to_user(buf, &ev, sizeof(ev)))
        return -EFAULT;

    return sizeof(ev);
}

static __poll_t hte_clock_poll(struct file *file, poll_table *wait)
{
    struct hte_clock_dev *priv = file->private_data;
    __poll_t mask = 0;

    poll_wait(file, &priv->readq, wait);

    if (!kfifo_is_empty(&priv->fifo))
        mask |= POLLIN | POLLRDNORM;

    return mask;
}

static int hte_clock_open(struct inode *inode, struct file *file)
{
    struct miscdevice *misc = file->private_data;
    struct hte_clock_dev *priv;

    priv = container_of(misc, struct hte_clock_dev, miscdev);
    file->private_data = priv;

    return 0;
}

static const struct file_operations hte_clock_fops = {
    .owner = THIS_MODULE,
    .open = hte_clock_open,
    .read = hte_clock_read,
    .poll = hte_clock_poll,
    .llseek = no_llseek,
};

static int hte_clock_probe(struct platform_device *pdev)
{
    struct hte_clock_dev *priv;
    struct device *dev = &pdev->dev;
    int ret;

    priv = devm_kzalloc(dev, sizeof(*priv), GFP_KERNEL);
    if (!priv)
        return -ENOMEM;

    priv->dev = dev;
    platform_set_drvdata(pdev, priv);

    spin_lock_init(&priv->fifo_lock);
    init_waitqueue_head(&priv->readq);
    atomic64_set(&priv->dropped, 0);

    ret = kfifo_alloc(&priv->fifo, HTE_CLOCK_FIFO_DEPTH, GFP_KERNEL);
    if (ret) {
        dev_err(dev, "failed to allocate fifo: %d\n", ret);
        return ret;
    }

    /*
     * Get input GPIO from:
     *
     *   in-gpios = <&gpio_aon 9 0>;
     */
    priv->in_gpio = devm_gpiod_get(dev, "in", GPIOD_IN);
    if (IS_ERR(priv->in_gpio)) {
        ret = PTR_ERR(priv->in_gpio);
        dev_err(dev, "failed to get input gpio: %d\n", ret);
        goto err_fifo;
    }

    priv->irq = gpiod_to_irq(priv->in_gpio);
    if (priv->irq < 0) {
        ret = priv->irq;
        dev_err(dev, "failed to convert gpio to irq: %d\n", ret);
        goto err_fifo;
    }

    dev_info(dev, "input gpio irq=%d\n", priv->irq);

    /*
     * Configure the GPIO IRQ as rising edge, but do not request an IRQ
     * handler. HTE will timestamp the edge; this just sets up the edge
     * type for the GPIO/IRQ path.
     */
    ret = irq_set_irq_type(priv->irq, IRQ_TYPE_EDGE_RISING);
    if (ret) {
        dev_err(dev, "failed to set gpio irq type rising: %d\n", ret);
        goto err_fifo;
    }

    /*
     * Get HTE descriptor from:
     *
     *   timestamps = <&hte_aon 9>;
     */
    ret = hte_ts_get(dev, &priv->desc, 0);
    if (ret) {
        dev_err(dev, "failed to get HTE timestamp desc: %d\n", ret);
        goto err_fifo;
    }

    /*
     * Initialize HTE line attributes.
     *
     * HTE_EDGE_NO_SETUP means the consumer/IRQ path already configured
     * the edge. We pass the GPIO descriptor as line_data so the provider
     * can associate the HTE line with the GPIO if required.
     */
    ret = hte_init_line_attr(&priv->desc,
                 priv->desc.attr.line_id,
                 HTE_EDGE_NO_SETUP,
                 "external-clock",
                 priv->in_gpio);
    if (ret) {
        dev_err(dev, "failed to init HTE line attr: %d\n", ret);
        goto err_hte_put;
    }

    dev_info(dev,
         "requesting HTE line_id=%u edge_flags=%lu line_data=%px\n",
         priv->desc.attr.line_id,
         priv->desc.attr.edge_flags,
         priv->desc.attr.line_data);

    /*
     * Request HTE timestamp callback in nanoseconds.
     */
    ret = devm_hte_request_ts_ns(dev,
                     &priv->desc,
                     hte_clock_cb,
                     NULL,
                     priv);
    if (ret) {
        dev_err(dev, "failed to request HTE timestamps: %d\n", ret);
        goto err_hte_put;
    }

    ret = hte_enable_ts(&priv->desc);
    if (ret) {
        dev_err(dev, "failed to enable HTE timestamps: %d\n", ret);
        goto err_hte_put;
    }

    priv->hte_enabled = true;

    priv->miscdev.minor = MISC_DYNAMIC_MINOR;
    priv->miscdev.name = "hte_clock0";
    priv->miscdev.fops = &hte_clock_fops;
    priv->miscdev.parent = dev;

    ret = misc_register(&priv->miscdev);
    if (ret) {
        dev_err(dev, "failed to register misc device: %d\n", ret);
        goto err_hte_disable;
    }

    dev_info(dev,
         "registered /dev/hte_clock0 for rising-edge HTE line %u\n",
         priv->desc.attr.line_id);

    return 0;

err_hte_disable:
    if (priv->hte_enabled)
        hte_disable_ts(&priv->desc);

err_hte_put:
    hte_ts_put(&priv->desc);

err_fifo:
    kfifo_free(&priv->fifo);
    return ret;
}

static int hte_clock_remove(struct platform_device *pdev)
{
    struct hte_clock_dev *priv = platform_get_drvdata(pdev);

    misc_deregister(&priv->miscdev);

    if (priv->hte_enabled)
        hte_disable_ts(&priv->desc);

    hte_ts_put(&priv->desc);

    kfifo_free(&priv->fifo);

    dev_info(&pdev->dev,
         "removed hte_clock driver, dropped=%lld\n",
         atomic64_read(&priv->dropped));

    return 0;
}

static const struct of_device_id hte_clock_of_match[] = {
    { .compatible = "custom,hte-clock" },
    { }
};
MODULE_DEVICE_TABLE(of, hte_clock_of_match);

static struct platform_driver hte_clock_driver = {
    .probe = hte_clock_probe,
    .remove = hte_clock_remove,
    .driver = {
        .name = "hte-clock",
        .of_match_table = hte_clock_of_match,
    },
};

module_platform_driver(hte_clock_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("custom");
MODULE_DESCRIPTION("Custom rising-edge HTE GPIO external clock timestamp driver");
