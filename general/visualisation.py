"""
Helper functions
"""
import matplotlib.pyplot as plt
import matplotlib.colors
import pandas as pd

def hex_rgb(hex):
    if hex == '@android:color/black': return (0, 0, 0)
    elif hex.startswith('@color/material_deep_teal'): return (0, 95, 95)
    elif hex.startswith('@color/material_grey') or hex.startswith('@color/roo_default_color_gray_dim'): return (80,80, 80)
    elif hex.startswith('@color/material_white') or hex.startswith('@android:color/white'): return (255, 255, 255)
    elif hex.startswith('@color/base_sdl_primary_negative_text_holo_dark'): return (0,0, 0)
    elif hex.startswith('@color/base_sdl_primary_positive_text_holo_dark'): return (255,255,255)
    elif hex.startswith('@color/bright_foreground_material_light'): return (255,255,255)
    elif hex.startswith('@color/bright_foreground_material_dark'): return (0,0,0)
    elif hex.startswith('@android:color/transparent'): return (255,255,255)
    elif hex.startswith('@color/button_normal'): return (255,255,255)
    elif hex.startswith('@color/xm_sdk_text_color_black') or hex.startswith('@color/base_text_black'): return (255,255,255)
    elif hex.startswith('@color/second_grey') or hex.startswith('@color/xm_sdk_text_color_dark_gray') or hex.startswith('@color/base_black_primary') or hex.startswith('@color/xm_sdk_text_color_gray') : return (169,169,169)
    elif hex.startswith('@color/xm_sdk_main_blue'): return (0,0,255)
    elif hex.startswith('@color/white') or hex.startswith('@color/xm_sdk_white') or hex.startswith('@color/xm_sdk_text_color_white'): return (0,0,0)
    elif hex.startswith('@color/xm_sdk_out_link_message_color'): return (0,0,0)
    elif hex.startswith('@color/default_style_color'): return (0,0,0)
    elif hex.startswith('@color/retail_white') or hex.startswith('@color/text_white') or hex.startswith('@color/crop_color_white') or hex.startswith('@color/xm_sdk_default_white') or hex.startswith('@color/hk_common_white'): return (0,0,0)
    elif hex.startswith('r/h/') or hex.startswith('r/w/') : return (0,0,0)
    elif hex.startswith('res-54/'): return (0,0,0)
    elif hex.startswith('@color/base_color_primary'): return (0,0,0)
    elif hex.startswith('@color/crop_color_black'): return (255,255,255)
    elif hex.startswith('@color/red_FF5F59'): return matplotlib.colors.to_rgb('#FF5F59')
    elif hex.startswith('@color/meetingTextColorSecond'): return matplotlib.colors.to_rgb('#FF5F59')
    elif hex.startswith('@color/mtpaysdk__button_textcolor_selector'): return matplotlib.colors.to_rgb('#FF5F59')
    elif hex.startswith('@color/divider_line'): return (0,0,0)
    elif hex.startswith('@color/text_green'): return (164,198,57)
    elif hex.startswith('@color/retail_theme_color') or hex.startswith('@color/theme_color'): return (164,198,57)
    elif hex.startswith('@color/paybase__weak_guide_color'): return (164,198,57)
    elif hex.startswith('@color/paybase__background_main_color1'): return (164,198,57)
    elif hex.startswith('@color/yellow_FFD161'): return matplotlib.colors.to_rgb('#FFD161')
    elif hex.startswith('@color/retail_product_base_color_'): return matplotlib.colors.to_rgb('#'+ hex.replace('@color/retail_product_base_color_',''))
    elif hex.startswith('@color/retail_food_label_selected_category_color'): return (0,0,0)
    elif hex.startswith('@color/retail_orange'): return (255,140,0)
    elif hex.startswith('@color/roo_default_color_gray_light') or hex.startswith('@color/third_grey') : return (211,211,211)
    elif hex.startswith('@color/meetingTextColorDisable'): return (255,140,0)
    else:
        return  matplotlib.colors.to_rgb(hex)
    if hex.startswith('#'):
        h = hex[1:]
        if h.startswith("000"): h="000000"
        if h.startswith("fff"): return (255, 255, 255)
        if h.startswith("666"): h="666666"
        if h.startswith("999"): h="999999"
        if h.startswith("888"): h="888888"
        if h.startswith("777"): h="777777"
        if h.startswith("555"): h="555555"
        if h.startswith("444"): h="444444"
        if h.startswith("333"): h="333333"
        if h.startswith("222"): h="222222"
        if h.startswith("ddd"): return (221, 221, 255)
        if h.startswith("ccc"): h="cccccc"
        if h.startswith("eee"): h="eeeeee"
        if h.startswith("ff00"): h="ff0000"
        print(h)
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

colours = pd.read_csv("/Users/iain/Desktop/all_colours.csv")
colours.columns = ["app", "func", "hex"]
x = colours["func"]
y = colours["app"]
colors = colours["hex"].map(hex_rgb)
#area = (30 * np.random.rand(N))**2  # 0 to 15 point radii

plt.scatter(x, y, c=colors)
plt.show() 