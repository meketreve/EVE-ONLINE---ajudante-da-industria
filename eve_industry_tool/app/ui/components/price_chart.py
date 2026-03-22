"""
Price and volume chart components using NiceGUI ECharts.
"""

from nicegui import ui


def render_price_charts(history: list[dict], item_name: str = ""):
    """
    Renderiza gráficos de volume (barras) e preço (linha) com ECharts.

    Parameters
    ----------
    history : list of dicts with keys: date, volume, lowest, average, highest
    item_name : str - used in chart titles
    """
    if not history:
        return

    dates   = [h["date"]    for h in history]
    volumes = [h["volume"]  for h in history]
    lows    = [h["lowest"]  for h in history]
    avgs    = [h["average"] for h in history]
    highs   = [h["highest"] for h in history]

    # Gráfico de volume
    with ui.card().classes("q-pa-md bg-grey-9 w-full q-mb-md"):
        ui.label("Volume Diário").classes("text-subtitle1 text-white q-mb-sm font-bold")
        vol_chart = ui.echart({
            "backgroundColor": "transparent",
            "tooltip":  {"trigger": "axis"},
            "xAxis":    {"type": "category", "data": dates, "axisLabel": {"color": "#9e9e9e"}},
            "yAxis":    {"type": "value", "axisLabel": {"color": "#9e9e9e", "formatter": "{value}"}},
            "grid":     {"left": "5%", "right": "2%", "bottom": "8%", "top": "5%"},
            "series": [
                {
                    "name": "Volume",
                    "type": "bar",
                    "data": volumes,
                    "itemStyle": {"color": "#546e7a"},
                    "emphasis":  {"itemStyle": {"color": "#78909c"}},
                }
            ],
        }).classes("w-full h-48")

    # Gráfico de preço
    with ui.card().classes("q-pa-md bg-grey-9 w-full q-mb-md"):
        ui.label("Histórico de Preços").classes("text-subtitle1 text-white q-mb-sm font-bold")
        price_chart = ui.echart({
            "backgroundColor": "transparent",
            "tooltip":  {"trigger": "axis"},
            "legend":   {"data": ["Mínimo", "Médio", "Máximo"], "textStyle": {"color": "#9e9e9e"}},
            "xAxis":    {"type": "category", "data": dates, "axisLabel": {"color": "#9e9e9e"}},
            "yAxis":    {"type": "value", "axisLabel": {"color": "#9e9e9e"}},
            "grid":     {"left": "5%", "right": "2%", "bottom": "8%", "top": "10%"},
            "series": [
                {
                    "name": "Mínimo",
                    "type": "line",
                    "data": lows,
                    "smooth": True,
                    "lineStyle": {"color": "#ef5350"},
                    "itemStyle": {"color": "#ef5350"},
                    "symbol":    "none",
                },
                {
                    "name": "Médio",
                    "type": "line",
                    "data": avgs,
                    "smooth": True,
                    "lineStyle": {"color": "#42a5f5", "width": 2},
                    "itemStyle": {"color": "#42a5f5"},
                    "symbol":    "none",
                    "areaStyle": {"color": "rgba(66,165,245,0.1)"},
                },
                {
                    "name": "Máximo",
                    "type": "line",
                    "data": highs,
                    "smooth": True,
                    "lineStyle": {"color": "#66bb6a"},
                    "itemStyle": {"color": "#66bb6a"},
                    "symbol":    "none",
                },
            ],
        }).classes("w-full h-48")
