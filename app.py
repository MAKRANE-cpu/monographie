import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Chefchaouen Analytics", page_icon="🌿", layout="wide")

# --- 2. FONCTION DE NETTOYAGE ---
def clean_val(val):
    if val is None or val == "": return 0.0
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

# --- 3. CHARGEMENT DES DONNÉES ---
@st.cache_data(ttl=600)
def load_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    
    all_data = {}
    for ws in sh.worksheets():
        raw = ws.get_all_values()
        if not raw: continue
        
        # Détection du header "Commune"
        h_idx = -1
        for i, r in enumerate(raw):
            if "commune" in [str(c).lower().strip() for c in r]:
                h_idx = i
                break
        if h_idx == -1: continue

        # Construction des noms de colonnes
        cols = []
        main = ""
        for c1, c2 in zip(raw[h_idx], raw[h_idx+1] if h_idx+1 < len(raw) else raw[h_idx]):
            if c1.strip(): main = c1.strip()
            name = f"{main}_{c2.strip()}" if c2.strip() and main != c2.strip() else main
            cols.append(name if name else "Info")
        
        df = pd.DataFrame(raw[h_idx+2:], columns=cols)
        for c in df.columns:
            if "Commune" not in c: df[c] = df[c].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 4. LOGIQUE PRINCIPALE ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur : {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🌿 Menu")
    page = st.radio("Aller à", ["📊 Dashboard Interactif", "🤖 Expert IA (Analyse de données)"])
    if st.button("🔄 Actualiser les données"):
        st.cache_data.clear()
        st.rerun()

# --- PAGES ---
if page == "📊 Dashboard Interactif":
    st.title("📊 Visualisation des Données")
    onglet = st.selectbox("Sélectionnez une catégorie", list(data_dict.keys()))
    df = data_dict[onglet]
    
    num_cols = [c for c in df.columns if "Commune" not in c]
    if num_cols:
        target = st.selectbox("Donnée à analyser", num_cols)
        fig = px.bar(df.sort_values(target, ascending=False), x="Commune", y=target, 
                     color=target, color_continuous_scale="Greens",
                     title=f"Classement des communes par {target}")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write(df)

elif page == "🤖 Expert IA (Analyse de données)":
    st.title("🤖 Expert IA Décisionnel")
    st.info("L'IA a accès à la feuille sélectionnée pour vous aider dans vos analyses.")

    if "gemini_api_key" not in st.secrets:
        st.error("Clé API manquante.")
    else:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Choix de la feuille sur laquelle l'IA doit travailler
        onglet_ia = st.selectbox("Sur quelle catégorie l'IA doit-elle travailler ?", list(data_dict.keys()))
        df_context = data_dict[onglet_ia]

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])

        if prompt := st.chat_input("Ex: Analyse les rendements et dis-moi quelle commune est la plus efficace ?"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            # --- LE SECRET EST ICI : Envoyer le tableau complet sous forme de texte ---
            # On convertit le tableau en format CSV (très léger en tokens)
            csv_data = df_context.to_csv(index=False)
            
            full_prompt = f"""
            Tu es un expert agronome analyste pour la province de Chefchaouen.
            Voici les données complètes de la catégorie '{onglet_ia}' :
            
            {csv_data}
            
            En te basant UNIQUEMENT sur ces chiffres, réponds à la question suivante : {prompt}
            Sois précis, cite des noms de communes et des chiffres exacts.
            """

            with st.chat_message("assistant"):
                with st.spinner("L'IA analyse le tableau..."):
                    try:
                        response = model.generate_content(full_prompt)
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})
                    except Exception as e:
                        st.error(f"Erreur IA : {e}")