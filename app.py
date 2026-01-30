import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re
from datetime import datetime
import json
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Agri-Analytics Chefchaouen",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLE PERSONNALISÉ ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2E8B57;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #3CB371;
        font-weight: 600;
        margin-bottom: 1rem;
    }
    .card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        border-left: 5px solid #2E8B57;
    }
    .metric-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stButton>button {
        background-color: #2E8B57;
        color: white;
        font-weight: 600;
        border: none;
        padding: 10px 24px;
        border-radius: 8px;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #3CB371;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2E8B57;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES SPÉCIFIQUES ---
def clean_val(val):
    """Nettoyage robuste des valeurs numériques"""
    if pd.isna(val) or val in ["", None]:
        return 0.0
    s = str(val).strip()
    s = re.sub(r'[\s\xa0,]+', '', s)
    match = re.search(r"[-+]?\d*\.?\d+", s)
    return float(match.group()) if match else 0.0

def smart_detect_header(raw_data):
    """Détection intelligente de l'en-tête dans les données brutes"""
    header_candidates = []
    
    for i, row in enumerate(raw_data[:10]):  # Regarder les 10 premières lignes
        row_lower = [str(cell).lower().strip() for cell in row]
        
        # Critères pour identifier un en-tête
        score = 0
        if "commune" in row_lower:
            score += 10
        if any(x in row_lower for x in ["sup", "ha", "surface", "rendement", "nbre", "capacité"]):
            score += 5
        if any(x in row_lower for x in ["total", "moyenne", "somme"]):
            score += 2
        
        if score > 0:
            header_candidates.append((i, score))
    
    if header_candidates:
        # Retourner l'en-tête avec le score le plus élevé
        header_candidates.sort(key=lambda x: x[1], reverse=True)
        return header_candidates[0][0]
    
    return 0  # Fallback: première ligne

def process_sheet_data(raw_data, sheet_name):
    """Traitement intelligent des données d'une feuille spécifique"""
    if not raw_data:
        return pd.DataFrame()
    
    # Détection intelligente de l'en-tête
    header_row = smart_detect_header(raw_data)
    
    # Pour les feuilles complexes, utiliser un traitement spécial
    complex_sheets = ['CLASSE TAILLE DES EXPLO', 'PRODUCTION VEGETALE Céréales', 
                     'Légumineuses', 'Plantation fruitière 1', 'Fourrages']
    
    if sheet_name in complex_sheets:
        return process_complex_sheet(raw_data, header_row, sheet_name)
    else:
        return process_standard_sheet(raw_data, header_row, sheet_name)

def process_standard_sheet(raw_data, header_row, sheet_name):
    """Traitement des feuilles standard"""
    try:
        # Prendre les données à partir de la ligne d'en-tête
        data_rows = raw_data[header_row:]
        
        # La première ligne après l'en-tête contient souvent des sous-titres
        if len(data_rows) > 1:
            # Combiner l'en-tête et la sous-ligne si nécessaire
            header = data_rows[0]
            sub_header = data_rows[1] if len(data_rows) > 1 else header
            
            # Créer des noms de colonnes combinés
            column_names = []
            for i, (h, sh) in enumerate(zip(header, sub_header)):
                h_str = str(h).strip()
                sh_str = str(sh).strip()
                
                if h_str and sh_str and h_str != sh_str:
                    col_name = f"{h_str} - {sh_str}"
                elif h_str:
                    col_name = h_str
                elif sh_str:
                    col_name = sh_str
                else:
                    col_name = f"Colonne_{i+1}"
                
                column_names.append(col_name)
            
            # Créer le DataFrame à partir de la 3ème ligne
            df_data = data_rows[2:] if len(data_rows) > 2 else []
        else:
            column_names = [str(cell).strip() for cell in data_rows[0]]
            df_data = data_rows[1:] if len(data_rows) > 1 else []
        
        # Créer le DataFrame
        df = pd.DataFrame(df_data, columns=column_names)
        
        # Nettoyer les noms de colonnes
        df.columns = [clean_column_name(col) for col in df.columns]
        
        # Nettoyer les données
        for col in df.columns:
            if col.lower() != 'commune':
                df[col] = df[col].apply(clean_val)
        
        return df
        
    except Exception as e:
        st.warning(f"Problème avec la feuille {sheet_name}: {str(e)}")
        # Fallback: retourner un DataFrame vide
        return pd.DataFrame()

def process_complex_sheet(raw_data, header_row, sheet_name):
    """Traitement spécial pour les feuilles complexes"""
    try:
        # Pour les feuilles complexes, on prend un approche plus simple
        # On cherche la première ligne contenant 'Commune'
        data_start = header_row
        
        # Prendre les 2 lignes suivantes comme en-têtes potentiels
        headers = raw_data[data_start:data_start+2]
        
        # Construire les noms de colonnes
        col_names = []
        for i in range(len(headers[0])):
            main = str(headers[0][i]).strip() if i < len(headers[0]) else ""
            sub = str(headers[1][i]).strip() if len(headers) > 1 and i < len(headers[1]) else ""
            
            if main and sub and main != sub:
                col_name = f"{main} - {sub}"
            elif main:
                col_name = main
            elif sub:
                col_name = sub
            else:
                col_name = f"Col_{i+1}"
            
            col_names.append(col_name)
        
        # Prendre les données à partir de la ligne 3
        data_rows = raw_data[data_start+2:]
        
        # Créer le DataFrame
        df = pd.DataFrame(data_rows, columns=col_names)
        
        # Nettoyer les noms de colonnes
        df.columns = [clean_column_name(col) for col in df.columns]
        
        # Nettoyer les données
        for col in df.columns:
            if 'commune' not in col.lower():
                df[col] = df[col].apply(clean_val)
        
        return df
        
    except Exception as e:
        st.warning(f"Erreur dans la feuille complexe {sheet_name}: {str(e)}")
        return pd.DataFrame()

def clean_column_name(col_name):
    """Nettoie le nom de colonne"""
    if pd.isna(col_name):
        return "Colonne_inconnue"
    
    col_str = str(col_name).strip()
    
    # Remplacer les caractères problématiques
    col_str = col_str.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # Supprimer les espaces multiples
    col_str = re.sub(r'\s+', ' ', col_str)
    
    # Standardiser certains termes
    col_str = col_str.replace('Sup.', 'Sup').replace('Rdt.', 'Rdt')
    
    return col_str

def categorize_sheets(sheet_names):
    """Catégorise les feuilles par type"""
    categories = {}
    
    for sheet in sheet_names:
        sheet_lower = sheet.lower()
        
        if any(x in sheet_lower for x in ['superficie', 'repartition']):
            categories[sheet] = 'superficies'
        elif any(x in sheet_lower for x in ['juridique', 'statut']):
            categories[sheet] = 'statut_juridique'
        elif any(x in sheet_lower for x in ['taille', 'exploitation']):
            categories[sheet] = 'taille_exploitations'
        elif 'irrigation' in sheet_lower:
            categories[sheet] = 'irrigation'
        elif any(x in sheet_lower for x in ['animal', 'cheptel', 'bovin', 'ovin']):
            categories[sheet] = 'production_animale'
        elif 'apiculture' in sheet_lower:
            categories[sheet] = 'apiculture'
        elif any(x in sheet_lower for x in ['cereal', 'vegetal', 'legumineuse']):
            categories[sheet] = 'production_vegetale'
        elif any(x in sheet_lower for x in ['maraichage', 'maraîchage']):
            categories[sheet] = 'maraichage'
        elif any(x in sheet_lower for x in ['plantation', 'fruitier']):
            categories[sheet] = 'plantations'
        elif 'fourrage' in sheet_lower:
            categories[sheet] = 'fourrages'
        elif any(x in sheet_lower for x in ['pedologie', 'pente', 'relief']):
            categories[sheet] = 'pedologie'
        elif any(x in sheet_lower for x in ['industrie', 'cooperative']):
            categories[sheet] = 'agro_industrie'
        elif any(x in sheet_lower for x in ['population', 'demographie']):
            categories[sheet] = 'population'
        elif any(x in sheet_lower for x in ['climat', 'pluviometrie']):
            categories[sheet] = 'climat'
        else:
            categories[sheet] = 'autres'
    
    return categories

# --- CHARGEMENT ET PRÉTRAITEMENT DES DONNÉES SPÉCIFIQUES ---
@st.cache_data(ttl=600)
def load_and_process_data(sheet_id):
    """Charge et prétraite les données spécifiques de Chefchaouen"""
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=scope
        )
        client = gspread.authorize(creds)
        sh = client.open_by_key(sheet_id)
        
        all_data = {}
        successful_sheets = []
        failed_sheets = []
        
        for ws in sh.worksheets():
            try:
                st.info(f"Chargement de la feuille: {ws.title}")
                raw = ws.get_all_values()
                
                if not raw:
                    st.warning(f"Feuille {ws.title} vide")
                    continue
                
                # Traitement intelligent de la feuille
                df = process_sheet_data(raw, ws.title)
                
                if df.empty or len(df) < 2:
                    st.warning(f"Feuille {ws.title}: données insuffisantes")
                    continue
                
                # Vérifier et corriger la colonne "Commune"
                commune_col = None
                for col in df.columns:
                    if 'commune' in str(col).lower():
                        commune_col = col
                        break
                
                if commune_col:
                    # Renommer la colonne en "Commune" standard
                    df = df.rename(columns={commune_col: 'Commune'})
                    # Nettoyer les noms de communes
                    df['Commune'] = df['Commune'].astype(str).str.strip()
                    # Supprimer les lignes où Commune est vide ou NaN
                    df = df[df['Commune'].notna() & (df['Commune'] != '')]
                    # Supprimer les lignes de total
                    df = df[~df['Commune'].str.contains('total|TOTAL|Total|S/T', case=False, na=False)]
                else:
                    st.warning(f"Feuille {ws.title}: colonne 'Commune' non trouvée")
                    # Créer une colonne Commune factice si nécessaire
                    df['Commune'] = f"Feuille_{ws.title}"
                
                # Stocker les données
                all_data[ws.title] = df
                successful_sheets.append(ws.title)
                
                st.success(f"✓ {ws.title}: {len(df)} lignes, {len(df.columns)} colonnes")
                
            except Exception as e:
                failed_sheets.append((ws.title, str(e)))
                st.error(f"✗ {ws.title}: {str(e)}")
        
        # Catégorisation des feuilles
        sheet_categories = categorize_sheets(successful_sheets)
        
        # Résumé du chargement
        st.success(f"""
        Chargement terminé:
        - ✅ Feuilles chargées avec succès: {len(successful_sheets)}
        - ❌ Feuilles en échec: {len(failed_sheets)}
        - 📊 Total des données: {sum(len(df) for df in all_data.values())} lignes
        """)
        
        if failed_sheets:
            st.warning("Feuilles en échec:")
            for sheet, error in failed_sheets:
                st.write(f"- {sheet}: {error}")
        
        return all_data, sheet_categories
        
    except Exception as e:
        st.error(f"Erreur de chargement globale : {str(e)}")
        return {}, {}

def calculate_agricultural_metrics(data_dict):
    """Calcule les métriques agricoles clés"""
    metrics = {}
    
    # Superficie totale
    if 'REPARTITION DES SUPERFICIES' in data_dict:
        df = data_dict['REPARTITION DES SUPERFICIES']
        if 'Sup.Totale' in df.columns:
            metrics['superficie_totale'] = df['Sup.Totale'].sum()
    
    # SAU totale
    if 'REPARTITION DES SUPERFICIES' in data_dict:
        df = data_dict['REPARTITION DES SUPERFICIES']
        sau_cols = [c for c in df.columns if 'sau' in c.lower() or 's.au' in c.lower()]
        if sau_cols:
            metrics['sau_totale'] = df[sau_cols[0]].sum()
    
    # Irrigation
    if "L'IRRIGATION" in data_dict:
        df = data_dict["L'IRRIGATION"]
        irrig_cols = [c for c in df.columns if 'irrigation' in c.lower()]
        if irrig_cols:
            metrics['irrigation_totale'] = df[irrig_cols[0]].sum()
    
    return metrics

# --- INITIALISATION ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

# Interface de chargement
st.title("🌱 Agri-Analytics Chefchaouen")
st.markdown("### Chargement des données agricoles...")

try:
    with st.spinner("Connexion à Google Sheets et chargement des données..."):
        data_dict, sheet_categories = load_and_process_data(SHEET_ID)
        
        if not data_dict:
            st.error("❌ Aucune donnée n'a pu être chargée. Vérifiez:")
            st.error("1. L'ID Google Sheets est correct")
            st.error("2. Le compte de service a les permissions nécessaires")
            st.error("3. Les feuilles contiennent des données valides")
            st.stop()
        
        st.success(f"✅ Données chargées avec succès: {len(data_dict)} feuilles")
        
        # Afficher un aperçu
        st.markdown("### 📊 Aperçu des données chargées")
        
        for sheet_name, df in list(data_dict.items())[:5]:  # Afficher les 5 premières
            with st.expander(f"📄 {sheet_name} ({len(df)} lignes, {len(df.columns)} colonnes)"):
                st.dataframe(df.head(), use_container_width=True)
        
        # Calculer les métriques
        metrics = calculate_agricultural_metrics(data_dict)
        
        if metrics:
            st.markdown("### 📈 Métriques clés détectées")
            cols = st.columns(len(metrics))
            for idx, (key, value) in enumerate(metrics.items()):
                with cols[idx]:
                    st.metric(
                        key.replace('_', ' ').title(),
                        f"{value:,.0f} ha" if 'superficie' in key or 'sau' in key or 'irrigation' in key else f"{value:,.0f}"
                    )
        
except Exception as e:
    st.error(f"Erreur d'initialisation : {str(e)}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="main-header">🌿 Agri-Analytics</div>', unsafe_allow_html=True)
    st.markdown("### Province de Chefchaouen")
    st.divider()
    
    page = st.radio(
        "Navigation",
        ["🏠 Tableau de Bord", "📊 Visualisations", "🔍 Analyse Sectorielle", 
         "🤖 Assistant IA", "📈 Rapports Agricoles", "⚙️ Paramètres"],
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # Filtrage par commune
    if data_dict:
        communes_list = []
        for df in data_dict.values():
            if 'Commune' in df.columns:
                communes_list.extend(df['Commune'].dropna().unique().tolist())
        
        communes_list = sorted(list(set(communes_list)))
        
        if communes_list:
            st.markdown("### 🏘️ Sélection de Communes")
            selected_communes = st.multiselect(
                "Filtrer par communes",
                communes_list,
                default=communes_list[:3] if communes_list else []
            )
    
    st.divider()
    
    if st.button("🔄 Actualiser les Données", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- PAGE : TABLEAU DE BORD ---
if page == "🏠 Tableau de Bord":
    st.markdown('<div class="main-header">🌱 Tableau de Bord Agri-Analytics Chefchaouen</div>', unsafe_allow_html=True)
    
    # Statistiques générales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_sheets = len(data_dict)
        st.metric("Feuilles de données", total_sheets)
    
    with col2:
        total_rows = sum(len(df) for df in data_dict.values())
        st.metric("Lignes de données", f"{total_rows:,}")
    
    with col3:
        if data_dict:
            communes_set = set()
            for df in data_dict.values():
                if 'Commune' in df.columns:
                    communes_set.update(df['Commune'].dropna().unique())
            st.metric("Communes", len(communes_set))
    
    with col4:
        if sheet_categories:
            categories_count = len(set(sheet_categories.values()))
            st.metric("Catégories", categories_count)
    
    st.divider()
    
    # Liste des feuilles disponibles
    st.markdown("### 📋 Feuilles disponibles")
    
    categories = {}
    for sheet, cat in sheet_categories.items():
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(sheet)
    
    for category, sheets in categories.items():
        with st.expander(f"📁 {category.upper()} ({len(sheets)} feuilles)"):
            for sheet in sheets:
                df = data_dict[sheet]
                communes = df['Commune'].nunique() if 'Commune' in df.columns else 0
                st.write(f"**{sheet}**: {len(df)} lignes, {len(df.columns)} colonnes, {communes} communes")
    
    # Aperçu des données
    st.divider()
    st.markdown("### 🔍 Explorer les données")
    
    selected_sheet = st.selectbox(
        "Sélectionner une feuille à explorer",
        list(data_dict.keys())
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        tab1, tab2 = st.tabs(["📊 Données", "📈 Statistiques"])
        
        with tab1:
            st.dataframe(df, use_container_width=True)
        
        with tab2:
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if numeric_cols:
                for col in numeric_cols[:5]:  # Limiter aux 5 premières colonnes numériques
                    st.write(f"**{col}**")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Moyenne", f"{df[col].mean():.2f}")
                    col2.metric("Médiane", f"{df[col].median():.2f}")
                    col3.metric("Min", f"{df[col].min():.2f}")
                    col4.metric("Max", f"{df[col].max():.2f}")

# --- PAGE : VISUALISATIONS ---
elif page == "📊 Visualisations":
    st.markdown('<div class="main-header">📊 Visualisations Interactives</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible pour la visualisation")
        st.stop()
    
    # Sélection de la feuille
    selected_sheet = st.selectbox(
        "Sélectionner une feuille",
        list(data_dict.keys())
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        # Vérifier les colonnes disponibles
        if 'Commune' not in df.columns:
            st.warning("Cette feuille ne contient pas de colonne 'Commune'")
            st.dataframe(df, use_container_width=True)
            st.stop()
        
        # Colonnes numériques disponibles
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if not numeric_cols:
            st.warning("Aucune colonne numérique trouvée dans cette feuille")
            st.dataframe(df, use_container_width=True)
            st.stop()
        
        # Interface de visualisation
        col1, col2 = st.columns([1, 3])
        
        with col1:
            selected_column = st.selectbox(
                "Sélectionner une colonne à visualiser",
                numeric_cols
            )
            
            chart_type = st.selectbox(
                "Type de graphique",
                ["Barres verticales", "Barres horizontales", "Camembert", "Treemap"]
            )
            
            sort_order = st.selectbox(
                "Trier par",
                ["Valeur décroissante", "Valeur croissante", "Ordre alphabétique"]
            )
            
            max_items = st.slider("Nombre d'éléments à afficher", 5, 50, 15)
        
        with col2:
            # Préparation des données
            plot_df = df[['Commune', selected_column]].copy()
            plot_df = plot_df.dropna()
            
            # Trier selon la sélection
            if sort_order == "Valeur décroissante":
                plot_df = plot_df.sort_values(selected_column, ascending=False)
            elif sort_order == "Valeur croissante":
                plot_df = plot_df.sort_values(selected_column, ascending=True)
            else:  # Ordre alphabétique
                plot_df = plot_df.sort_values('Commune')
            
            # Limiter le nombre d'éléments
            plot_df = plot_df.head(max_items)
            
            # Créer le graphique
            if chart_type == "Barres verticales":
                fig = px.bar(
                    plot_df,
                    x='Commune',
                    y=selected_column,
                    title=f"{selected_column} par commune",
                    color=selected_column,
                    color_continuous_scale="viridis"
                )
                fig.update_layout(xaxis_tickangle=-45)
            
            elif chart_type == "Barres horizontales":
                fig = px.bar(
                    plot_df,
                    y='Commune',
                    x=selected_column,
                    title=f"{selected_column} par commune",
                    color=selected_column,
                    color_continuous_scale="viridis",
                    orientation='h'
                )
            
            elif chart_type == "Camembert":
                fig = px.pie(
                    plot_df,
                    values=selected_column,
                    names='Commune',
                    title=f"Répartition de {selected_column}"
                )
            
            else:  # Treemap
                fig = px.treemap(
                    plot_df,
                    path=['Commune'],
                    values=selected_column,
                    title=f"Treemap de {selected_column}"
                )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Statistiques
            with st.expander("📊 Statistiques détaillées"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total", f"{plot_df[selected_column].sum():,.2f}")
                col2.metric("Moyenne", f"{plot_df[selected_column].mean():,.2f}")
                col3.metric("Minimum", f"{plot_df[selected_column].min():,.2f}")
                col4.metric("Maximum", f"{plot_df[selected_column].max():,.2f}")

# --- PAGE : ASSISTANT IA ---
elif page == "🤖 Assistant IA":
    st.markdown('<div class="main-header">🤖 Assistant IA Décisionnel</div>', unsafe_allow_html=True)
    
    if "gemini_api_key" not in st.secrets:
        st.error("⚠️ Clé API Gemini manquante. Ajoutez-la dans les secrets Streamlit")
        st.code("""
        # Dans .streamlit/secrets.toml
        gemini_api_key = "votre_cle_api_ici"
        """)
        st.stop()
    
    # Configuration de l'IA
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Interface
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### 📋 Contexte d'Analyse")
        
        # Sélection des données pour l'IA
        available_sheets = list(data_dict.keys())
        selected_sheets = st.multiselect(
            "Sélectionner les données à analyser",
            available_sheets,
            default=available_sheets[:3] if available_sheets else []
        )
        
        # Suggestions de questions
        st.markdown("### 💡 Questions suggérées")
        
        suggestions = [
            "Quelles sont les communes avec la plus grande superficie agricole?",
            "Analyse les tendances de production agricole",
            "Propose des recommandations pour améliorer la productivité",
            "Quelles sont les forces et faiblesses de l'agriculture locale?",
            "Compare les différentes communes sur la base des données disponibles"
        ]
        
        for suggestion in suggestions:
            if st.button(suggestion, key=f"sugg_{suggestion[:20]}"):
                st.session_state.ia_question = suggestion
    
    with col2:
        st.markdown("### 💬 Dialogue avec l'Expert Agricole")
        
        # Initialisation de l'historique
        if "ia_history" not in st.session_state:
            st.session_state.ia_history = []
        
        # Affichage de l'historique
        for msg in st.session_state.ia_history[-5:]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # Saisie de la question
        question = st.chat_input("Posez votre question sur l'agriculture à Chefchaouen...")
        
        if question or 'ia_question' in st.session_state:
            if 'ia_question' in st.session_state:
                question = st.session_state.ia_question
                del st.session_state.ia_question
            
            # Ajout de la question à l'historique
            st.session_state.ia_history.append({"role": "user", "content": question})
            
            with st.chat_message("user"):
                st.markdown(question)
            
            # Préparation des données pour l'IA
            with st.spinner("🔍 L'IA analyse les données agricoles..."):
                try:
                    # Préparer un échantillon des données sélectionnées
                    context_data = ""
                    for sheet in selected_sheets:
                        if sheet in data_dict:
                            df = data_dict[sheet]
                            # Prendre un échantillon et convertir en texte
                            sample = df.head(5).to_string(index=False)
                            context_data += f"\n\n=== {sheet} ===\n{sample}"
                    
                    prompt = f"""
                    Tu es un expert agronome spécialiste de la province de Chefchaouen au Maroc.
                    
                    CONTEXTE:
                    - Province: Chefchaouen
                    - Type de données: Données agricoles de monographie
                    - Feuilles analysées: {', '.join(selected_sheets)}
                    
                    DONNÉES DISPONIBLES (échantillon):
                    {context_data[:3000]}
                    
                    INSTRUCTIONS:
                    1. Analyse les données de manière précise et objective
                    2. Fais référence aux communes spécifiques quand c'est pertinent
                    3. Propose des recommandations pratiques et réalisables
                    4. Structure ta réponse de manière claire et organisée
                    5. Sois concis mais complet
                    
                    QUESTION: {question}
                    
                    RÉPONSE (en français):
                    """
                    
                    # Appel à l'API
                    response = model.generate_content(prompt)
                    
                    # Affichage de la réponse
                    with st.chat_message("assistant"):
                        st.markdown(response.text)
                    
                    # Sauvegarde dans l'historique
                    st.session_state.ia_history.append({
                        "role": "assistant", 
                        "content": response.text
                    })
                    
                except Exception as e:
                    st.error(f"Erreur lors de l'analyse IA: {str(e)}")

# --- PAGE : RAPPORTS AGRICOLES ---
elif page == "📈 Rapports Agricoles":
    st.markdown('<div class="main-header">📈 Rapports Agricoles</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible pour générer des rapports")
        st.stop()
    
    tab1, tab2 = st.tabs(["📋 Rapport par Commune", "🌾 Rapport Global"])
    
    with tab1:
        st.markdown("### 🏘️ Rapport par Commune")
        
        # Sélection d'une commune
        communes_list = []
        for df in data_dict.values():
            if 'Commune' in df.columns:
                communes_list.extend(df['Commune'].dropna().unique().tolist())
        
        communes_list = sorted(list(set(communes_list)))
        
        if not communes_list:
            st.warning("Aucune commune trouvée dans les données")
            st.stop()
        
        selected_commune = st.selectbox(
            "Sélectionner une commune",
            communes_list
        )
        
        if selected_commune and st.button("📊 Générer le rapport communal", type="primary"):
            with st.spinner("Génération du rapport en cours..."):
                # Collecte des données pour la commune
                commune_data = []
                
                for sheet_name, df in data_dict.items():
                    if 'Commune' in df.columns:
                        commune_rows = df[df['Commune'] == selected_commune]
                        if not commune_rows.empty:
                            for _, row in commune_rows.iterrows():
                                for col in df.columns:
                                    if col != 'Commune' and pd.api.types.is_numeric_dtype(df[col]):
                                        value = row[col]
                                        if value != 0:  # Ignorer les valeurs nulles
                                            commune_data.append({
                                                'Feuille': sheet_name,
                                                'Variable': col,
                                                'Valeur': value
                                            })
                
                if commune_data:
                    commune_df = pd.DataFrame(commune_data)
                    
                    st.markdown(f"## 📋 Rapport pour {selected_commune}")
                    
                    # Vue synthétique
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Indicateurs trouvés", len(commune_df))
                    
                    with col2:
                        st.metric("Catégories de données", commune_df['Feuille'].nunique())
                    
                    with col3:
                        avg_value = commune_df['Valeur'].mean()
                        st.metric("Valeur moyenne", f"{avg_value:,.1f}")
                    
                    # Tableau détaillé
                    st.dataframe(
                        commune_df.sort_values('Valeur', ascending=False),
                        use_container_width=True
                    )
                    
                    # Graphique des principales valeurs
                    top_values = commune_df.nlargest(10, 'Valeur')
                    if not top_values.empty:
                        fig = px.bar(
                            top_values,
                            x='Variable',
                            y='Valeur',
                            color='Feuille',
                            title=f"Top 10 indicateurs - {selected_commune}",
                            labels={'Valeur': 'Valeur', 'Variable': 'Indicateur'}
                        )
                        fig.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Téléchargement
                    report_text = f"Rapport pour {selected_commune}\n\n"
                    for _, row in commune_df.iterrows():
                        report_text += f"{row['Feuille']} - {row['Variable']}: {row['Valeur']}\n"
                    
                    st.download_button(
                        label="📄 Télécharger le rapport",
                        data=report_text,
                        file_name=f"rapport_{selected_commune}.txt",
                        mime="text/plain"
                    )
                else:
                    st.warning(f"Aucune donnée significative trouvée pour la commune {selected_commune}")
    
    with tab2:
        st.markdown("### 🌾 Rapport Global")
        
        # Sélection des feuilles à inclure
        selected_sheets = st.multiselect(
            "Sélectionner les feuilles à inclure",
            list(data_dict.keys()),
            default=list(data_dict.keys())[:5] if data_dict else []
        )
        
        if st.button("📈 Générer le rapport global", type="primary"):
            with st.spinner("Analyse des données en cours..."):
                # Création du rapport
                report = f"""
# 🌱 RAPPORT AGRICOLE - Province de Chefchaouen
**Date de génération:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Feuilles analysées:** {', '.join(selected_sheets)}

## 📊 SYNTHÈSE GLOBALE
"""
                
                # Analyse par feuille
                for sheet in selected_sheets:
                    if sheet in data_dict:
                        df = data_dict[sheet]
                        
                        report += f"\n### 📄 {sheet}\n"
                        report += f"- **Nombre de lignes:** {len(df)}\n"
                        report += f"- **Nombre de colonnes:** {len(df.columns)}\n"
                        
                        if 'Commune' in df.columns:
                            communes = df['Commune'].nunique()
                            report += f"- **Communes représentées:** {communes}\n"
                        
                        # Colonnes numériques
                        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                        if numeric_cols:
                            report += "- **Variables numériques principales:**\n"
                            for col in numeric_cols[:5]:  # Limiter aux 5 premières
                                if df[col].sum() > 0:
                                    report += f"  - {col}: {df[col].sum():,.2f} (total)\n"
                
                # Affichage du rapport
                st.markdown(report)
                
                # Téléchargement
                st.download_button(
                    label="📄 Télécharger le rapport complet",
                    data=report,
                    file_name=f"rapport_agricole_chefchaouen_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

# --- PAGE : PARAMÈTRES ---
elif page == "⚙️ Paramètres":
    st.markdown('<div class="main-header">⚙️ Paramètres et Administration</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["🔧 Configuration", "📊 Données", "📚 Aide"])
    
    with tab1:
        st.markdown("### Configuration de l'Application")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**Version:** 3.1.0")
            st.info(f"**Feuilles chargées:** {len(data_dict)}")
            st.info(f"**ID Google Sheets:** {SHEET_ID}")
        
        with col2:
            st.info(f"**Dernière actualisation:** {datetime.now().strftime('%H:%M:%S')}")
            st.info(f"**Statut API Gemini:** {'✅ Configurée' if 'gemini_api_key' in st.secrets else '❌ Manquante'}")
        
        # Options d'affichage
        st.markdown("### Personnalisation")
        
        theme = st.selectbox(
            "Thème de couleur",
            ["Vert Agricole", "Bleu Marin", "Terre Cuite", "Classique"]
        )
        
        if st.button("💾 Enregistrer les préférences"):
            st.success("Préférences enregistrées!")
    
    with tab2:
        st.markdown("### Gestion des Données")
        
        # Vue d'ensemble
        overview_data = []
        for sheet_name, df in data_dict.items():
            overview_data.append({
                'Feuille': sheet_name,
                'Catégorie': sheet_categories.get(sheet_name, 'autre'),
                'Lignes': len(df),
                'Colonnes': len(df.columns),
                'Communes': df['Commune'].nunique() if 'Commune' in df.columns else 0
            })
        
        overview_df = pd.DataFrame(overview_data)
        st.dataframe(overview_df, use_container_width=True)
        
        # Export
        st.markdown("### Export des Données")
        
        export_sheet = st.selectbox(
            "Sélectionner une feuille à exporter",
            list(data_dict.keys())
        )
        
        if export_sheet:
            df = data_dict[export_sheet]
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📥 Exporter en CSV", use_container_width=True):
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="✅ Télécharger CSV",
                        data=csv,
                        file_name=f"{export_sheet}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                if st.button("📊 Exporter en Excel", use_container_width=True):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Données')
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="✅ Télécharger Excel",
                        data=excel_data,
                        file_name=f"{export_sheet}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    
    with tab3:
        st.markdown("### 📚 Guide d'Utilisation")
        
        with st.expander("🎯 Comment utiliser l'application"):
            st.markdown("""
            1. **Tableau de Bord**: Vue d'ensemble des données disponibles
            2. **Visualisations**: Graphiques interactifs par feuille et variable
            3. **Assistant IA**: Analyse intelligente avec l'IA Gemini
            4. **Rapports**: Génération de rapports par commune ou global
            5. **Paramètres**: Configuration et export des données
            """)
        
        st.markdown("### 📞 Support")
        st.caption("Pour toute question ou problème, consultez la documentation ou contactez le support technique.")
        
        if st.button("🔄 Réinitialiser l'application"):
            st.cache_data.clear()
            st.rerun()

# --- FOOTER ---
st.divider()
st.caption(f"Agri-Analytics Chefchaouen v3.1 • Données chargées: {len(data_dict)} feuilles • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")