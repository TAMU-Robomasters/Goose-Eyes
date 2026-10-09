ENEMY_COLOR = "RED"  # 'BLUE' or 'RED'

# HSV bounds passed to cv2.inRange -- tune before match
# red wraps around hue 0, so two ranges are combined
red_lower1 = (0, 120, 70)
red_upper1 = (10, 255, 255)
red_lower2 = (170, 120, 70)
red_upper2 = (180, 255, 255)

blue_lower = (100, 120, 70)
blue_upper = (130, 255, 255)
