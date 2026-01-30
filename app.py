import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Agri-Chefchaouen Data", page_icon="🌿", layout="wide")

# Style CSS pour améliorer l'interface
st.markdown("""
    <style>
    .main { background-color: #f9fbf9; }
    h1, h2 { color: #2e7d32; }
    .stDataFrame { border: 1px solid #e0e0e0; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- FONCTION UTILE : RENDRE LES COLONNES UNIQUES ---
def make_columns_unique(df):
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(cols[cols == dup].count())]
    df.columns = cols
    return df

# --- 2. CONNEXION GOOGLE SHEETS ---
@st.cache_data(ttl=600)
def load_gspread_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    sh = client.open_by_key(sheet_id)
    worksheets = sh.worksheets()
    
    all_data = {}
    for ws in worksheets:
        values = ws.get_all_values()
        if not values:
            continue
            
        df = pd.DataFrame(values)
        
        # Détection de la ligne d'en-tête (Commune)
        header_idx = 0
        for i, row in df.iterrows():
            if any("Commune" in str(v) for v in row.values):
                header_idx = i
                break
        
        # --- GESTION DES COLONNES FUSIONNÉES (Ex: BD -> Sup et Rdt) ---
        h1 = df.iloc[header_idx]      # Ligne avec BD, BT...
        h2 = df.iloc[header_idx + 1]  # Ligne avec Sup, Rdt...
        
        new_cols = []
        current_main_col = ""
        
        for c1, c2 in zip(h1, h2):
            c1 = str(c1).strip()
            c2 = str(c2).strip()
            
            # Si la case du haut n'est pas vide, on change de culture
            if c1 != "" and "Unnamed" not in c1:
                current_main_col = c1
            
            if "Commune" in c1 or "Commune" in c2:
                new_cols.append("Commune")
            elif c2 != "" and "Unnamed" not in c2:
                new_cols.append(f"{current_main_col}_{c2}")
            else:
                new_cols.append(current_main_col)
        
        df.columns = new_cols
        # On garde les données après les deux lignes d'en-tête
        df = df.iloc[header_idx + 2:].reset_index(drop=True)
        
        # Nettoyage final : colonnes uniques et suppression des vides
        df = make_columns_unique(df)
        df = df.loc[:, ~df.columns.str.contains('^$')]
        
        all_data[ws.title] = df
        
    return all_data

SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_gspread_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.info("Vérifiez que votre clé dans 'Secrets' s'appelle GEMINI_API_KEY et que le bloc [gcp_service_account] est complet.")
    st.stop()

# --- 3. CONFIGURATION IA (GEMINI) ---
# Correction de la KeyError : on utilise bien le nom du secret défini dans Streamlit
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# --- 4. BARRE LATÉRALE ---
with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    st.write("Analyse de la Monographie")
    st.markdown("---")
    page = st.radio("Menu", ["📊 Tableaux de Bord", "🤖 Expert IA", "📈 Graphiques"])

# --- 5. PAGES ---

if page == "📊 Tableaux de Bord":
    st.title("Exploration des Données")
    onglet = st.selectbox("Choisir une catégorie (Onglet)", list(data_dict.keys()))
    
    df_display = data_dict[onglet].copy()
    st.write(f"Données pour : **{onglet}**")
    
    # Sécurité anti-doublons avant affichage
    df_display = make_columns_unique(df_display)
    st.dataframe(df_display, use_container_width=True)
    
    st.download_button("📥 Télécharger en CSV", df_display.to_csv(index=False), "data.csv")

elif page == "🤖 Expert IA":
    st.title("Assistant IA Agricole")
    st.info("Posez des questions sur les surfaces, les types de sols ou les productions.")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Ex: Quel est le rendement moyen du Blé Dur (BD) ?")
    
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        context = ""
        for name, df in data_dict.items():
            context += f"\nFeuille {name}: Colonnes={list(df.columns)} | Aperçu={df.head(3).to_string()}\n"

        full_query = f"Tu es un expert agricole. Voici les données de Chefchaouen :\n{context}\n\nQuestion : {prompt}"
        
        with st.chat_message("assistant"):
            try:
                response = ai_model.generate_content(full_query)
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Erreur IA : {e}")

elif page == "📈 Graphiques":
    st.title("Visualisation Interactive")
    onglet = st.selectbox("Sélectionner la donnée", list(data_dict.keys()))
    df = data_dict[onglet].copy()
    
    # Nettoyage des nombres (remplace virgule par point)
    for col in df.columns:
        if col != "Commune":
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.').str.replace(' ', ''), errors='coerce')

    cols_numeriques = df.select_dtypes(include=['number']).columns.tolist()
    
    if cols_numeriques:
        c1, c2 = st.columns(2)
        with c1:
            y_col = st.selectbox("Valeur (Y)", cols_numeriques)
        with c2:
            chart_type = st.selectbox("Type", ["Barres", "Secteurs"])
            
        x_axis = "Commune" if "Commune" in df.columns else df.columns[0]
        
        if chart_type == "Barres":
            fig = px.bar(df, x=x_axis, y=y_col, color=y_col, title=f"{y_col} par Commune")
        else:
            fig = px.pie(df, names=x_axis, values=y_col, title=f"Répartition de {y_col}")
            
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aucune donnée chiffrée exploitable trouvée dans cet onglet.")