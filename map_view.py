"""Interactive HTML map (Folium / Leaflet): shadows, both routes, barriers and the decision."""

import folium
import geopandas as gpd
from shapely.geometry import mapping

import config

ROUTE_COLORS = {"Shortest": "#d1495b", "Shaded": "#1f6fb2"}


def build_map(area, network, routes, decision, summary_lines, start, end, out_path):
    lat, lon = config.AREA_CENTER
    buildings, trees = area.buildings, area.trees
    fmap = folium.Map(location=[lat, lon], zoom_start=16, tiles="OpenStreetMap", control_scale=True)

    # Shade layer (computed in metres, shown in lat/lon)
    if not network.shade.is_empty:
        shade = gpd.GeoSeries([network.shade.simplify(0.5)], crs=config.PROJECTED_CRS).to_crs("EPSG:4326")
        folium.GeoJson(mapping(shade.iloc[0]), name="Shade (buildings + trees)",
                       style_function=lambda _: {"fillColor": "#2b2d42", "color": "#2b2d42",
                                                 "weight": 0, "fillOpacity": 0.35}).add_to(fmap)

    folium.GeoJson(buildings[["height", "geometry"]].to_json(), name="Buildings",
                   style_function=lambda _: {"fillColor": "#b8b8b8", "color": "#8d8d8d",
                                             "weight": 1, "fillOpacity": 0.6},
                   tooltip=folium.GeoJsonTooltip(fields=["height"], aliases=["Height, m"])).add_to(fmap)

    tree_layer = folium.FeatureGroup(name="Trees")
    for geometry, kind in zip(trees.geometry, trees["kind"]):
        if geometry.geom_type == "Point":
            folium.CircleMarker([geometry.y, geometry.x], radius=3, color="#2d6a4f",
                                fill=True, fill_opacity=0.8).add_to(tree_layer)
        else:
            folium.GeoJson(mapping(geometry), style_function=lambda _: {"color": "#2d6a4f", "weight": 4}).add_to(tree_layer)
    tree_layer.add_to(fmap)

    # Routes: the recommended one on top, thick and solid
    for action in sorted(routes, key=lambda a: a == decision):
        stats = routes[action]["stats"]
        chosen = action == decision
        folium.PolyLine(
            area.route_latlon(routes[action]["result"].edges),
            color=ROUTE_COLORS[action], weight=8 if chosen else 5, opacity=0.95 if chosen else 0.75,
            dash_array=None if chosen else "8 8",
            tooltip=(f"{action}{' (recommended)' if chosen else ''}: {stats['length_m']:.0f} m, "
                     f"{stats['sun_share']:.0%} in sun, {stats['walk_min']:.1f} min"),
        ).add_to(fmap)

    for report in network.barriers:
        folium.Marker([report["lat"], report["lon"]],
                      tooltip=f"{report['name']} ({report['type']}, simulated report)",
                      icon=folium.Icon(color="orange", icon="exclamation-sign")).add_to(fmap)
    folium.Marker([start[1], start[2]], tooltip=f"Start: {start[0]}", icon=folium.Icon(color="green", icon="play")).add_to(fmap)
    folium.Marker([end[1], end[2]], tooltip=f"End: {end[0]}", icon=folium.Icon(color="darkblue", icon="flag")).add_to(fmap)

    panel = "".join(f"<div>{line}</div>" for line in summary_lines)
    legend = (
        f"<div style='position:fixed;top:12px;right:12px;z-index:9999;background:white;padding:10px 12px;"
        f"border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.25);font:13px/1.45 system-ui,sans-serif;max-width:330px'>"
        f"<b style='font-size:15px'>SAYA route</b>{panel}<hr style='margin:6px 0'>"
        f"<div><span style='color:{ROUTE_COLORS['Shortest']}'>&#9644;</span> Shortest accessible route</div>"
        f"<div><span style='color:{ROUTE_COLORS['Shaded']}'>&#9644;</span> Shaded accessible route</div>"
        f"<div>Solid and thick = recommended, dashed = alternative</div>"
        f"<div><span style='color:#2b2d42'>&#9632;</span> Shade at this time &nbsp; "
        f"<span style='color:#2d6a4f'>&#9679;</span> Trees &nbsp; "
        f"<span style='color:#f0932b'>&#9679;</span> Barrier report</div></div>"
    )
    fmap.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(position="bottomright").add_to(fmap)
    out_path.parent.mkdir(exist_ok=True)
    fmap.save(str(out_path))
    return out_path
