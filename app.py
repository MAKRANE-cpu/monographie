import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Chefchaouen Data", page_icon="🌿", layout="wide")

# --- 2. FONCTION DE CHARGEMENT CORRIGÉE ---
# On ajoute un paramètre pour forcer la mise à jour si besoin
@st.cache_data(ttl=600)
def load_gspread_data(sheet_id, force_update=False):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    sh = client.open_by_key(sheet_id)
    worksheets = sh.worksheets()
    
    all_data = {}
    for ws in worksheets:
        values = ws.get_all_values()
        if not values: continue
            
        df_raw = pd.DataFrame(values)
        
        # --- DÉTECTION DYNAMIQUE DE L'EN-TÊTE ---
        header_idx = None
        for i, row in df_raw.iterrows():
            # On cherche la ligne qui contient "Commune" (peu importe la casse)
            if any("commune" in str(v).lower() for v in row.values):
                header_idx = i
                break
        
        if header_idx is not None:
            # Ligne des noms (ex: BD, Fève) et ligne des unités (Sup, Rdt)
            h_names = df_raw.iloc[header_idx]
            # On vérifie si une ligne d'unités existe juste en dessous
            h_units = df_raw.iloc[header_idx + 1] if (header_idx + 1) < len(df_raw) else None
            
            new_cols = []
            current_main = ""
            
            for idx, col_name in enumerate(h_names):
                col_name = str(col_name).strip()
                unit_name = str(h_units[idx]).strip() if h_units is not None else ""
                
                # Mise à jour du nom de la culture si la case n'est pas vide
                if col_name != "" and "unnamed" not in col_name.lower():
                    current_main = col_name
                
                if "commune" in col_name.lower() or "commune" in unit_name.lower():
                    new_cols.append("Commune")
                elif unit_name != "":
                    # Fusionne le nom de la culture et l'unité (ex: Fève_Sup)
                    new_cols.append(f"{current_main}_{unit_name}")
                else:
                    new_cols.append(current_main if current_main != "" else f"Col_{idx}")

            df_raw.columns = new_cols
            # On saute les lignes d'en-tête pour les données
            df = df_raw.iloc[header_idx + 2:].reset_index(drop=True)
        else:
            # Si pas de ligne "Commune", on prend la première ligne (cas secours)
            df = df_raw.copy()
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)

        # Nettoyage des colonnes vides et doublons
        df = df.loc[:, ~df.columns.duplicated()]
        df = df.loc[:, df.columns.notna()]
        all_data[ws.title] = df
        
    return all_data

# --- 3. INITIALISATION ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

# Bouton de mise à jour dans la barre latérale
with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    if st.button("🔄 Actualiser les données"):
        st.cache_data.clear() # Vide le cache pour forcer la lecture de Google Sheets
        st.success("Données mises à jour !")
    
    page = st.radio("Menu", ["📊 Tableaux de Bord", "🤖 Expert IA", "📈 Graphiques"])

try:
    data_dict = load_gspread_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur : {e}")
    st.stop()

# --- 4. AFFICHAGE (EXEMPLE TABLEAU) ---
if page == "📊 Tableaux de Bord":
    st.title("Exploration des Données")
    onglet = st.selectbox("Sélectionner une feuille", list(data_dict.keys()))
    
    df = data_dict[onglet].copy()
    
    # Nettoyage numérique pour l'affichage
    for col in df.columns:
        if col != "Commune":
            # Remplace virgules par points et gère les espaces
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.').str.replace(r'\s+', '', regex=True), errors='ignore')
    
    st.dataframe(df, use_container_width=True)

# ... (Le reste du code pour IA et Graphiques reste identique au précédent)
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