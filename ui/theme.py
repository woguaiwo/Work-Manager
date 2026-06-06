"""
Theme constants for Work Manager (工作管理系统)
Lightweight theming groundwork — colors are centralized here.
"""

THEME = {
    # Sidebar
    'sidebar_bg': '#E8D5C4',
    'sidebar_text': '#4a3f35',
    'sidebar_text_secondary': '#7a6f65',
    'sidebar_hover': '#D4C4B5',
    'sidebar_checked': '#C4B4A5',
    'sidebar_accent': '#8B7355',

    # Cards / Frames
    'card_bg': '#ffffff',
    'card_border': '#f0f0f0',
    'card_shadow': '#e0e0e0',

    # Accent colors for dashboard cards
    'accent_blue': '#5B8DB8',
    'accent_red': '#D4766A',
    'accent_green': '#7CB87A',
    'accent_orange': '#D4A76A',
    'accent_purple': '#9B8BB8',

    # Global
    'bg_window': '#f5f7fa',
    'text_primary': '#37474f',
    'text_secondary': '#78909c',
    'border_light': '#e8e8e8',
}


def get_color(key: str) -> str:
    return THEME.get(key, '#000000')
