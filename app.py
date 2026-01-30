import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Agri-Chefchaouen Dashboard", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FONCTIONS DE NETTOYAGE ---
def clean_val(val):
    """Nettoie une cellule individuelle pour en faire un nombre"""
    if val is None or val == "":
        return 0.0
    # On garde seulement les chiffres, les points et les virgules
    s = str(val).strip().replace(' ', '').replace('\xa0', '')
    s = s.replace(',', '.')
    # Extraire le premier nombre trouvé (ignore le texte autour)
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    if match:
        try:
            return float(match.group())
        except:
            return 0.0
    return 0.0

@st.cache_data(ttl=600)
def load_and_fix_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    
    all_data = {}
    for ws in sh.worksheets():
        rows = ws.get_all_values()
        if not rows: continue
        
        df_raw = pd.DataFrame(rows)
        
        # Trouver la ligne "Commune"
        header_idx = 0
        for i, row in df_raw.iterrows():
            if any("commune" in str(v).lower() for v in row.values):
                header_idx = i
                break
        
        # Fusionner les en-têtes (ex: Blé Dur + Sup = Blé Dur_Sup)
        h1 = df_raw.iloc[header_idx]
        h2 = df_raw.iloc[header_idx + 1] if (header_idx + 1) < len(df_raw) else h1
        
        new_cols = []
        current_main = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = str(c1).strip(), str(c2).strip()
            if c1 != "" and "unnamed" not in c1.lower():
                current_main = c1
            
            if "commune" in c1.lower() or "commune" in c2.lower():
                new_cols.append("Commune")
            elif c2 != "":
                new_cols.append(f"{current_main}_{c2}")
            else:
                new_cols.append(current_main if current_main else "Info")
        
        df = df_raw.iloc[header_idx+2:].copy()
        df.columns = new_cols
        
        # NETTOYAGE : On applique clean_val cellule par cellule pour éviter l'erreur .str
        for col in df.columns:
            if "Commune" not in col:
                df[col] = df[col].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 3. LOGIQUE INITIALE ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_and_fix_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.stop()

# --- 4. NAVIGATION SIDEBAR ---
with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    page = st.radio("Menu", ["📊 Dashboard", "🤖 Expert IA", "📂 Données Brutes"])
    if st.button("🔄 Actualiser les données"):
        st.cache_data.clear()
        st.rerun()

# --- 5. PAGES ---

if page == "📊 Dashboard":
    st.title("📊 Analyses des Productions")
    
    onglet = st.selectbox("Sélectionnez une catégorie", list(data_dict.keys()))
    df = data_dict[onglet]
    
    # KPIs
    c1, c2, c3 = st.columns(3)
    num_cols = [c for c in df.columns if c != "Commune"]
    
    if num_cols:
        target = st.selectbox("Choisir une variable à visualiser", num_cols)
        
        with c1: st.metric("Total", f"{df[target].sum():,.0f}")
        with c2: st.metric("Moyenne", f"{df[target].mean():.2f}")
        with c3: st.metric("Max (Commune)", f"{df[target].max():,.0f}")
        
        # Graphique Plotly
        fig = px.bar(df, x="Commune", y=target, color=target, 
                     color_continuous_scale="Greens", template="plotly_white",
                     title=f"Répartition de {target} par Commune")
        st.plotly_chart(fig, use_container_width=True)
        
        # Graphique de synthèse (Top 5)
        st.subheader("🔝 Top 10 des Communes")
        top_10 = df.nlargest(10, target)
        fig_pie = px.pie(top_10, names="Commune", values=target, hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.warning("Pas de données numériques trouvées.")

elif page == "🤖 Expert IA":
    st.title("🤖 Expert IA")
    if "gemini_api_key" not in st.secrets:
        st.error("Configurez 'gemini_api_key' dans les secrets Streamlit.")
    else:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for m in st.session_state.chat_history:
            with st.chat_message(m["role"]): st.markdown(m["content"])

        if prompt := st.chat_input("Ex: Analyse le rendement du Blé Dur..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            # Contexte : On donne les 5 premières lignes de la feuille actuelle à l'IA
            current_data = list(data_dict.values())[0].head(10).to_string()
            
            with st.chat_message("assistant"):
                response = model.generate_content(f"Données provinciales :\n{current_data}\n\nQuestion : {prompt}")
                st.markdown(response.text)
                st.session_state.chat_history.append({"role": "assistant", "content": response.text})

elif page == "📂 Données Brutes":
    st.title("📂 Explorateur de Tableaux")
    onglet = st.selectbox("Feuille", list(data_dict.keys()), key="raw_sel")
    st.dataframe(data_dict[onglet], use_container_width=True)