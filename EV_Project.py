import streamlit as st
import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd
import heapq

st.set_page_config(layout="wide", page_title="⚡ EV Charging Optimizer + Advisor")

# Helper: build graph from text input
def parse_edges(text):
    G = nx.Graph()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        u, v, w = parts[0], parts[1], float(parts[2])
        G.add_node(u)
        G.add_node(v)
        G.add_edge(u, v, weight=w)
    return G

# Visualization
def draw_graph(G, chargers=set(), new=set(), path=None, recharge_nodes=None, highlight_node=None, title="Graph"):
    fig, ax = plt.subplots(figsize=(7, 5))
    pos = nx.spring_layout(G, seed=42)
    node_colors = []
    for n in G.nodes:
        if highlight_node and n == highlight_node:
            node_colors.append("#d291bc")
        elif recharge_nodes and n in recharge_nodes:
            node_colors.append("#f28585")
        elif n in new:
            node_colors.append("#ffb347")
        elif n in chargers:
            node_colors.append("#66c2a5")
        else:
            node_colors.append("#89CFF0")
            
    nx.draw(G, pos, with_labels=True, node_color=node_colors, node_size=800, font_size=10, ax=ax)
    edge_labels = nx.get_edge_attributes(G, 'weight')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=9, ax=ax)
    if path:
        edges_in_path = list(zip(path, path[1:]))
        nx.draw_networkx_edges(G, pos, edgelist=edges_in_path, edge_color='red', width=3, ax=ax)
    ax.set_title(title, fontsize=12, fontweight='bold')
    st.pyplot(fig)
    plt.close(fig)

# K-center Greedy Approximation
def k_center_with_existing(G, k_new, existing_chargers):
    nodes = list(G.nodes)
    if not nodes or k_new <= 0:
        return []
    centers = list(existing_chargers)[:] if existing_chargers else [nodes[0]]
    target_count = len(existing_chargers) + k_new
    while len(centers) < target_count:
        max_dist, far_node = -1, None
        for n in nodes:
            if n in centers:
                continue
            dists = []
            for c in centers:
                try:
                    d = nx.shortest_path_length(G, n, c, weight="weight")
                except nx.NetworkXNoPath:
                    d = float('inf')
                dists.append(d)
            min_dist = min(dists) if dists else float('inf')
            if min_dist > max_dist:
                max_dist = min_dist
                far_node = n
        if far_node is None or far_node in centers:
            break
        centers.append(far_node)
    return [c for c in centers if c not in existing_chargers]

# Battery-safe routing using State-Space Priority Queue
def battery_safe_route(G, source, target, battery_capacity, initial_battery, chargers_set):
    pq = [(0.0, source, initial_battery, [source], [])]
    visited = set()
    while pq:
        cost, node, battery, path, recharges = heapq.heappop(pq)
        key = (node, round(battery, 1))
        if key in visited:
            continue
        visited.add(key)

        if node == target:
            avg_km = cost / (len(recharges) + 1) if recharges else cost
            return path, cost, recharges, avg_km

        if node in chargers_set and node != source:
            battery = battery_capacity
            if node not in recharges:
                recharges = recharges + [node]

        for nb in G.neighbors(node):
            dist = G[node][nb]['weight']
            if battery >= dist:
                new_cost = cost + dist
                new_battery = battery - dist
                heapq.heappush(pq, (new_cost, nb, new_battery, path + [nb], recharges[:]))
    return None, float('inf'), [], None

# Dynamic Convoy Station Decision Heuristic
def station_decision(distance_to_station, distance_to_next, current_battery, evs_waiting, station_capacity, charge_time, battery_capacity):
    if current_battery < distance_to_station:
        return "❌ Cannot reach this station."
    battery_after_station = current_battery - distance_to_station
    wait_time_here = (evs_waiting / station_capacity) * charge_time if station_capacity > 0 else float('inf')
    can_skip = battery_after_station >= distance_to_next
    if not can_skip:
        return f"⚡ Must stop. Wait ≈ {round(wait_time_here)} min."
    if wait_time_here < charge_time:
        return f"👍 Better to stop here. Wait ≈ {round(wait_time_here)} min."
    else:
        return f"➡️ Better to skip. Next station {distance_to_next} km ahead. Battery left after reaching = {round(battery_after_station - distance_to_next, 1)} km."


# STREAMLIT UI
st.title("⚡ EV Charging Network Optimizer + Dynamic Convoy Advisor")
st.markdown("Optimize EV charging infrastructure placement, calculate battery-safe routes, and get real-time station stop recommendations.")

# Sidebar Controls
with st.sidebar.expander("1) Graph Input", expanded=True):
    st.markdown("Enter edges: `u v distance`")
    default = "A B 40\nB C 20\nC D 25\nB E 30\nE F 20"
    edges_text = st.text_area("Edges (u v weight)", value=default, height=140)
    G = parse_edges(edges_text)

nodes = list(G.nodes)
if not nodes:
    st.warning("Graph is empty — please enter valid edges in the sidebar.")
    st.stop()

with st.sidebar.expander("2) Charging Stations", expanded=True):
    default_chargers = [n for n in ["B", "C", "E"] if n in nodes] or ([nodes[0]] if nodes else [])
    chargers = st.multiselect("Select existing chargers", nodes, default=default_chargers)
    station_capacity = st.number_input("Plugs / Chargers per station", min_value=1, max_value=20, value=2)
    charge_time = st.number_input("Charging time per EV (minutes)", min_value=5, max_value=240, value=30)

with st.sidebar.expander("3) Battery Setup", expanded=True):
    battery_capacity = st.slider("Battery capacity (km)", min_value=10, max_value=500, value=100)
    initial_battery = st.slider("Initial battery (km)", min_value=0, max_value=battery_capacity, value=min(60, battery_capacity))

with st.sidebar.expander("4) K-Center Optimization", expanded=True):
    k_new = st.number_input("New stations to add (k)", min_value=0, max_value=len(nodes), value=1)
    if st.button("Run K-Center"):
        new_centers = k_center_with_existing(G, k_new, set(chargers))
        st.session_state['new_centers'] = new_centers
        st.success(f"Suggested new stations: {new_centers}")

new_centers = st.session_state.get('new_centers', [])
all_chargers_set = set(chargers) | set(new_centers)

st.markdown("---")
tab1, tab2, tab3 = st.tabs(["📊 Network Graph & Optimization", "🔋 Range Anxiety Routing", "🚗 Convoy Advisor"])

# TAB 1: Graph + Optimizer
with tab1:
    st.subheader("Network Graph Overview")
    col1, col2 = st.columns([3, 2])
    with col1:
        draw_graph(G, chargers=set(chargers), new=set(new_centers), title="EV Network Topology")
    with col2:
        st.markdown("### Network Details")
        st.write("**Total Nodes:**", len(nodes), f"(`{', '.join(nodes)}`)")
        st.write("**Existing Chargers:**", chargers if chargers else "None")
        st.write("**Optimized New Stations (K-Center):**", new_centers if new_centers else "None")
        
        st.markdown("### Edge Distances")
        edge_data = [{"From": u, "To": v, "Distance (km)": G[u][v]['weight']} for u, v in G.edges]
        st.dataframe(pd.DataFrame(edge_data), use_container_width=True)

# TAB 2: Range Anxiety
with tab2:
    st.subheader("Battery-Safe Route Planning")
    st.markdown("Finds a reachable path ensuring the battery level never drops below zero, planning recharge stops automatically.")
    
    col_src, col_dst = st.columns(2)
    with col_src:
        src = st.selectbox("Source Node", nodes, index=0)
    with col_dst:
        dst = st.selectbox("Destination Node", nodes, index=max(0, len(nodes) - 1))
        
    if st.button("Find Safe Route", type="primary"):
        path, dist, recharges, avg_km = battery_safe_route(G, src, dst, battery_capacity, initial_battery, all_chargers_set)
        if not path:
            st.error(f"❌ No battery-safe path could be found from **{src}** to **{dst}** with battery {initial_battery} km and capacity {battery_capacity} km.")
            st.session_state['route_path'] = None
            st.session_state['route_dist'] = None
            st.session_state['route_recharges'] = []
            st.session_state['route_avg_km'] = None
        else:
            st.session_state['route_path'] = path
            st.session_state['route_dist'] = dist
            st.session_state['route_recharges'] = recharges
            st.session_state['route_avg_km'] = avg_km
            st.session_state['route_src'] = src
            st.session_state['route_dst'] = dst

    if st.session_state.get('route_path'):
        p = st.session_state['route_path']
        d = st.session_state['route_dist']
        r = st.session_state['route_recharges']
        a_km = st.session_state['route_avg_km']
        
        st.success(f"**Feasible Route Found:** {' ➔ '.join(p)} (Total Distance: **{d} km**)")
        if r:
            st.info(f"**Recharge Stops Needed:** {', '.join(r)}")
        else:
            st.info("No recharge needed! Destination reached on initial battery.")
            
        if a_km:
            st.write(f"**Average distance per leg/recharge:** ≈ `{round(a_km, 1)} km`")
            
        draw_graph(G, chargers=set(chargers), new=set(new_centers), path=p, recharge_nodes=r, title=f"Safe Route: {p[0]} to {p[-1]}")

# TAB 3: Convoy Advisor (Decision)
with tab3:
    st.subheader("Dynamic Convoy Advisor")
    st.markdown("Provides real-time decisions at intermediate charging stations considering queue lengths and wait times.")
    
    current_path = st.session_state.get('route_path')
    if not current_path:
        st.info("ℹ️ Please compute a route in the **'Range Anxiety Routing'** tab first.")
    else:
        st.markdown(f"**Current Evaluated Route:** `{' ➔ '.join(current_path)}`")
        stations_on_path = [n for i, n in enumerate(current_path[:-1]) if n in all_chargers_set]
        
        all_chargers_list = sorted(list(all_chargers_set))
        waiting_info = {}
        if all_chargers_list:
            st.write("##### Current EV Queue at Stations:")
            cols = st.columns(min(len(all_chargers_list), 4) or 1)
            for idx, ch in enumerate(all_chargers_list):
                with cols[idx % len(cols)]:
                    waiting_info[ch] = st.number_input(f"EVs at Station {ch}", min_value=0, max_value=50, value=2, key=f"wait_{ch}")
        
        st.write("##### 📍 Recommendations along route:")
        if not stations_on_path:
            st.write("No intermediate charging stations along this specific route.")
        else:
            for i, node in enumerate(current_path):
                if node in all_chargers_set and node != current_path[-1]:
                    dist_to_here = sum(G[current_path[j]][current_path[j+1]]['weight'] for j in range(i))
                    dist_to_next = G[current_path[i]][current_path[i+1]]['weight'] if i+1 < len(current_path) else float('inf')
                    decision = station_decision(
                        dist_to_here,
                        dist_to_next,
                        initial_battery,
                        waiting_info.get(node, 0),
                        station_capacity,
                        charge_time,
                        battery_capacity
                    )
                    st.markdown(f"- **Station {node}:** {decision}")
