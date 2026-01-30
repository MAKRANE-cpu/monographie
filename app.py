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

def calculate_production(df):
    """Calcule la production totale à partir des surfaces et rendements"""
    production_data = []
    
    # Détection automatique des colonnes de surface et rendement
    for col in df.columns:
        if 'Sup' in col or 'sup' in col or 'ha' in col or 'Ha' in col:
            # Chercher la colonne de rendement correspondante
            for rdt_col in df.columns:
                if ('Rdt' in rdt_col or 'rdt' in rdt_col or 'Qx' in rdt_col or 
                    'qx' in rdt_col or 'QX' in rdt_col) and rdt_col != col:
                    try:
                        # Calculer la production
                        prod_col = f"{col}_Production"
                        df[prod_col] = df[col] * df[rdt_col]
                        production_data.append({
                            'variable': col.replace('_Sup', '').replace('_ha', ''),
                            'surface_totale': df[col].sum(),
                            'production_totale': df[prod_col].sum(),
                            'rendement_moyen': df[rdt_col].mean()
                        })
                    except:
                        continue
    return production_data

def analyze_commune_performance(df, commune_col="Commune"):
    """Analyse la performance de chaque commune"""
    if commune_col not in df.columns:
        return None
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    performance = []
    
    for commune in df[commune_col].unique():
        commune_data = df[df[commune_col] == commune]
        metrics = {'Commune': commune}
        
        for col in numeric_cols:
            if col != commune_col:
                metrics[f'{col}_moyenne'] = commune_data[col].mean()
                metrics[f'{col}_total'] = commune_data[col].sum()
        
        # Calculer un score agrégé (simple somme des valeurs normalisées)
        score = 0
        for col in numeric_cols:
            if col != commune_col and df[col].max() > 0:
                normalized = commune_data[col].mean() / df[col].max()
                score += normalized
        
        metrics['score_performance'] = score
        performance.append(metrics)
    
    return pd.DataFrame(performance)

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
        sheet_categories = {}
        
        # Catégorisation des feuilles
        categories = {
            'superficies': ['REPARTITION DES SUPERFICIES'],
            'statut_juridique': ['STATUT JURIDIQUE DES TERRES AGR'],
            'taille_exploitations': ['CLASSE TAILLE DES EXPLO'],
            'irrigation': ["L'IRRIGATION"],
            'production_animale': ['PRODUCTION ANIMALE', 'Feuil18'],
            'apiculture': ['APICULTURE'],
            'cereales': ['PRODUCTION VEGETALE Céréales'],
            'legumineuses': ['Légumineuses'],
            'maraichage': ['Maraîchage 1', 'Maraichage 2', 'Maraichage 3'],
            'plantations': ['Plantation fruitière 1', 'Plantation fruitière 2'],
            'fourrages': ['Fourrages'],
            'pedologie': ['PENTES ET RELIEF', 'PEDOLOGIE 1', 'PEDOLOGIE 2'],
            'agro_industrie': ['AGRO - INDUSTRIE'],
            'infrastructures': ['Abattoirs', 'lait'],
            'population': ['POPULATION'],
            'climat': ['CLIMAT', 'PLUVIOMETRIE PAR STATION'],
            'organisations': ['COOPERATIVES', 'AVICULTURE']
        }
        
        for ws in sh.worksheets():
            raw = ws.get_all_values()
            if not raw:
                continue
            
            # Détection du header
            h_idx = -1
            for i, r in enumerate(raw):
                if "commune" in [str(c).lower().strip() for c in r]:
                    h_idx = i
                    break
            if h_idx == -1:
                continue
            
            # Construction des colonnes avec traitement spécial pour les tables complexes
            if ws.title in ['CLASSE TAILLE DES EXPLO', 'Légumineuses', 'Maraîchage 1', 
                           'Plantation fruitière 1', 'Fourrages']:
                # Traitement spécial pour les tables à structure complexe
                df = process_complex_table(raw, h_idx)
            else:
                # Construction standard des colonnes
                cols = []
                main = ""
                for c1, c2 in zip(raw[h_idx], raw[h_idx+1] if h_idx+1 < len(raw) else raw[h_idx]):
                    if c1.strip():
                        main = c1.strip()
                    name = f"{main} - {c2.strip()}" if c2.strip() and main != c2.strip() else main
                    cols.append(name if name else "Info")
                
                df = pd.DataFrame(raw[h_idx+2:], columns=cols)
            
            # Nettoyage des données
            for c in df.columns:
                if "Commune" not in c and c != "Info" and not df[c].empty:
                    try:
                        df[c] = df[c].apply(clean_val)
                    except:
                        pass
            
            # Ajout d'identifiant unique pour chaque commune
            if 'Commune' in df.columns:
                df['commune_id'] = df['Commune'].astype(str).str.lower().str.strip()
            
            all_data[ws.title] = df.reset_index(drop=True)
            
            # Catégoriser la feuille
            for cat, sheets in categories.items():
                if ws.title in sheets:
                    sheet_categories[ws.title] = cat
                    break
            else:
                sheet_categories[ws.title] = 'autres'
        
        return all_data, sheet_categories
        
    except Exception as e:
        st.error(f"Erreur de chargement : {str(e)}")
        return {}, {}

def process_complex_table(raw, h_idx):
    """Traite les tables complexes avec structure imbriquée"""
    # Cette fonction traite les tables comme 'CLASSE TAILLE DES EXPLO'
    # qui ont des en-têtes complexes
    df_list = []
    
    # Extraction des noms de colonnes de base
    base_cols = []
    for cell in raw[h_idx]:
        if cell.strip():
            base_cols.append(cell.strip())
    
    # Création du DataFrame
    data_rows = raw[h_idx+2:]
    df = pd.DataFrame(data_rows, columns=base_cols[:len(data_rows[0])])
    
    return df

def create_agricultural_report(data_dict, selected_sheets):
    """Crée un rapport agricole complet"""
    report = f"""
# 🌱 RAPPORT AGRICOLE COMPLET - Province de Chefchaouen
**Date de génération:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Données analysées:** {', '.join(selected_sheets)}

## 📊 SYNTHÈSE GLOBALE
"""
    
    # Analyse des superficies
    if 'REPARTITION DES SUPERFICIES' in data_dict:
        df_sup = data_dict['REPARTITION DES SUPERFICIES']
        report += "\n### 🗺️ SUPERFICIES TOTALES\n"
        total_surface = df_sup['Sup.Totale'].sum() if 'Sup.Totale' in df_sup.columns else 0
        report += f"- **Superficie totale de la province:** {total_surface:,.0f} ha\n"
        
        if 'S.AU_Total' in df_sup.columns:
            sau_totale = df_sup['S.AU_Total'].sum()
            report += f"- **Surface Agricole Utile (SAU):** {sau_totale:,.0f} ha "
            report += f"({sau_totale/total_surface*100:.1f}% de la superficie totale)\n"
    
    # Analyse de la production végétale
    if 'PRODUCTION VEGETALE Céréales' in data_dict:
        df_cereales = data_dict['PRODUCTION VEGETALE Céréales']
        report += "\n### 🌾 PRODUCTION CÉRÉALIÈRE\n"
        
        cereales_cols = [c for c in df_cereales.columns if 'Sup' in c and 'BD' in c or 'BT' in c or 'OG' in c]
        for col in cereales_cols[:3]:  # Limiter aux 3 premières céréales
            culture = col.replace('_Sup', '')
            surface = df_cereales[col].sum()
            report += f"- **{culture}:** {surface:,.0f} ha\n"
    
    # Analyse de la production animale
    if 'PRODUCTION ANIMALE' in data_dict:
        df_anim = data_dict['PRODUCTION ANIMALE']
        report += "\n### 🐄 CHEPTEL ANIMAL\n"
        
        if 'Bovins_Locales' in df_anim.columns:
            bovins = df_anim['Bovins_Locales'].sum()
            report += f"- **Bovins locaux:** {bovins:,.0f} têtes\n"
        
        if 'Ovins' in df_anim.columns:
            ovins = df_anim['Ovins'].sum()
            report += f"- **Ovins:** {ovins:,.0f} têtes\n"
    
    # Analyse de l'irrigation
    if "L'IRRIGATION" in data_dict:
        df_irrig = data_dict["L'IRRIGATION"]
        report += "\n### 💧 IRRIGATION\n"
        
        if 'sup irrigation Ha' in df_irrig.columns:
            irrig_totale = df_irrig['sup irrigation Ha'].sum()
            report += f"- **Surface irriguée totale:** {irrig_totale:,.0f} ha\n"
    
    return report

# --- INITIALISATION ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict, sheet_categories = load_and_process_data(SHEET_ID)
    if not data_dict:
        st.error("Aucune donnée trouvée. Vérifiez l'ID de la feuille.")
        st.stop()
except Exception as e:
    st.error(f"Erreur d'initialisation : {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="main-header">🌿 Agri-Analytics</div>', unsafe_allow_html=True)
    st.markdown("### Province de Chefchaouen")
    st.divider()
    
    page = st.radio(
        "Navigation",
        ["🏠 Tableau de Bord", "📊 Visualisations", "🔍 Analyse Sectorielle", 
         "🤖 Assistant IA", "📈 Rapports Agricoles", "🗺️ Cartographie", "⚙️ Paramètres"],
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # Sélection rapide de communes
    st.markdown("### 🏘️ Sélection de Communes")
    communes_list = []
    for df in data_dict.values():
        if 'Commune' in df.columns:
            communes_list.extend(df['Commune'].dropna().unique().tolist())
    
    communes_list = sorted(list(set(communes_list)))
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
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown('<div class="main-header">🌱 Tableau de Bord Agri-Analytics Chefchaouen</div>', unsafe_allow_html=True)
        st.markdown("### Surveillance et Analyse des Données Agricoles 2012")
    
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**📊 Catégories de Données**")
        categories_count = {}
        for cat in sheet_categories.values():
            categories_count[cat] = categories_count.get(cat, 0) + 1
        
        for cat, count in list(categories_count.items())[:5]:
            st.caption(f"• {cat}: {count} feuille(s)")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # KPI Agricoles
    st.markdown("### 📈 INDICATEURS CLÉS AGRICOLES")
    
    # Calcul des KPI à partir des données
    kpi_data = []
    
    # Superficie totale
    if 'REPARTITION DES SUPERFICIES' in data_dict:
        df_sup = data_dict['REPARTITION DES SUPERFICIES']
        if 'Sup.Totale' in df_sup.columns:
            total_surface = df_sup['Sup.Totale'].sum()
            kpi_data.append(("Superficie Totale", f"{total_surface:,.0f} ha", "🗺️"))
    
    # SAU Totale
    if 'REPARTITION DES SUPERFICIES' in data_dict:
        df_sup = data_dict['REPARTITION DES SUPERFICIES']
        sau_cols = [c for c in df_sup.columns if 'S.AU' in c and 'Total' in c]
        if sau_cols:
            sau_totale = df_sup[sau_cols[0]].sum()
            kpi_data.append(("Surface Agricole Utile", f"{sau_totale:,.0f} ha", "🌾"))
    
    # Irrigation
    if "L'IRRIGATION" in data_dict:
        df_irrig = data_dict["L'IRRIGATION"]
        if 'sup irrigation Ha' in df_irrig.columns:
            irrig_totale = df_irrig['sup irrigation Ha'].sum()
            kpi_data.append(("Surface Irriguée", f"{irrig_totale:,.0f} ha", "💧"))
    
    # Production animale
    if 'PRODUCTION ANIMALE' in data_dict:
        df_anim = data_dict['PRODUCTION ANIMALE']
        animal_cols = [c for c in df_anim.columns if 'Bovins' in c or 'Ovins' in c or 'Caprins' in c]
        if animal_cols:
            total_animaux = df_anim[animal_cols[0]].sum()
            kpi_data.append(("Cheptel (Bovins)", f"{total_animaux:,.0f} têtes", "🐄"))
    
    # Affichage des KPI
    cols = st.columns(min(4, len(kpi_data)))
    for idx, (title, value, icon) in enumerate(kpi_data):
        with cols[idx % len(cols)]:
            st.markdown(f'<div class="metric-card">', unsafe_allow_html=True)
            st.metric(f"{icon} {title}", value)
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Graphique de synthèse
    st.divider()
    st.markdown("### 📊 RÉPARTITION PAR SECTEUR")
    
    # Préparation des données pour le graphique sectoriel
    sector_data = []
    
    # Calcul des surfaces par type d'utilisation
    if 'REPARTITION DES SUPERFICIES' in data_dict:
        df_sup = data_dict['REPARTITION DES SUPERFICIES']
        
        # Détection des colonnes de types de terres
        terre_cols = [c for c in df_sup.columns if any(x in c for x in ['Forêt', 'Parcours', 'Inculte', 'Bour', 'Irriguée'])]
        
        for col in terre_cols:
            total = df_sup[col].sum()
            if total > 0:
                secteur = col.split('_')[-1] if '_' in col else col
                sector_data.append({
                    'Secteur': secteur,
                    'Superficie (ha)': total,
                    'Type': 'Occupation des sols'
                })
    
    # Calcul des productions végétales
    if 'PRODUCTION VEGETALE Céréales' in data_dict:
        df_cereales = data_dict['PRODUCTION VEGETALE Céréales']
        cereales_cols = [c for c in df_cereales.columns if 'Sup' in c]
        
        for col in cereales_cols[:5]:  # Limiter aux 5 premières
            total = df_cereales[col].sum()
            if total > 0:
                cereale = col.replace('_Sup', '').replace('_', ' ')
                sector_data.append({
                    'Secteur': cereale,
                    'Superficie (ha)': total,
                    'Type': 'Céréales'
                })
    
    if sector_data:
        sector_df = pd.DataFrame(sector_data)
        
        tab1, tab2 = st.tabs(["📈 Graphique", "📋 Données"])
        
        with tab1:
            fig = px.treemap(
                sector_df,
                path=['Type', 'Secteur'],
                values='Superficie (ha)',
                title='Répartition des surfaces agricoles',
                color='Superficie (ha)',
                color_continuous_scale='Greens'
            )
            fig.update_layout(margin=dict(t=50, l=25, r=25, b=25))
            st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            st.dataframe(
                sector_df.sort_values('Superficie (ha)', ascending=False),
                use_container_width=True
            )

# --- PAGE : VISUALISATIONS ---
elif page == "📊 Visualisations":
    st.markdown('<div class="main-header">📊 Visualisations Interactives</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["🌾 Production", "🐄 Élevage", "💧 Irrigation", "📋 Données Brutes"])
    
    with tab1:
        st.markdown("### 🌾 ANALYSE DE LA PRODUCTION VÉGÉTALE")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # Sélection des cultures
            culture_options = []
            if 'PRODUCTION VEGETALE Céréales' in data_dict:
                culture_options.append(('Céréales', 'PRODUCTION VEGETALE Céréales'))
            if 'Légumineuses' in data_dict:
                culture_options.append(('Légumineuses', 'Légumineuses'))
            if 'Maraîchage 1' in data_dict:
                culture_options.append(('Maraîchage', 'Maraîchage 1'))
            
            selected_culture = st.selectbox(
                "Type de culture",
                [opt[0] for opt in culture_options],
                index=0 if culture_options else None
            )
            
            if selected_culture:
                selected_sheet = [opt[1] for opt in culture_options if opt[0] == selected_culture][0]
                df = data_dict[selected_sheet]
                
                # Détection des colonnes de surface
                surface_cols = [c for c in df.columns if any(x in c for x in ['Sup', 'sup', 'ha', 'Ha'])]
                
                if surface_cols:
                    selected_variable = st.selectbox(
                        "Variable à analyser",
                        surface_cols
                    )
                    
                    # Options de visualisation
                    chart_type = st.selectbox(
                        "Type de graphique",
                        ["Barres", "Camembert", "Treemap"]
                    )
                    
                    top_n = st.slider("Nombre de communes à afficher", 5, 30, 10)
        
        with col2:
            if selected_culture and 'selected_variable' in locals():
                st.markdown(f"### {selected_culture} - {selected_variable}")
                
                # Préparation des données
                plot_df = df[['Commune', selected_variable]].copy()
                plot_df = plot_df.dropna()
                plot_df = plot_df.sort_values(selected_variable, ascending=False).head(top_n)
                
                if chart_type == "Barres":
                    fig = px.bar(
                        plot_df,
                        x='Commune',
                        y=selected_variable,
                        color=selected_variable,
                        color_continuous_scale="viridis",
                        title=f"Top {top_n} communes - {selected_variable}"
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    
                elif chart_type == "Camembert":
                    fig = px.pie(
                        plot_df,
                        values=selected_variable,
                        names='Commune',
                        title=f"Répartition - {selected_variable}"
                    )
                    
                else:  # Treemap
                    fig = px.treemap(
                        plot_df,
                        path=['Commune'],
                        values=selected_variable,
                        title=f"Treemap - {selected_variable}"
                    )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Statistiques
                with st.expander("📊 Statistiques détaillées"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total", f"{plot_df[selected_variable].sum():,.0f}")
                    col2.metric("Moyenne", f"{plot_df[selected_variable].mean():,.1f}")
                    col3.metric("Maximum", f"{plot_df[selected_variable].max():,.0f}")
    
    with tab2:
        st.markdown("### 🐄 ANALYSE DU CHEPTEL ANIMAL")
        
        if 'PRODUCTION ANIMALE' in data_dict:
            df_anim = data_dict['PRODUCTION ANIMALE']
            
            # Détection des types d'animaux
            animal_types = [c for c in df_anim.columns if any(x in c for x in ['Bovins', 'Ovins', 'Caprins', 'Chevaux', 'Mulets', 'Anes'])]
            
            if animal_types:
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    selected_animal = st.selectbox(
                        "Type d'animal",
                        animal_types
                    )
                    
                    # Comparaison multiple
                    compare_animals = st.multiselect(
                        "Comparer plusieurs types",
                        animal_types,
                        default=animal_types[:min(3, len(animal_types))]
                    )
                
                with col2:
                    if selected_animal:
                        # Graphique pour un type d'animal
                        fig1 = px.bar(
                            df_anim.sort_values(selected_animal, ascending=False).head(15),
                            x='Commune',
                            y=selected_animal,
                            title=f"Distribution de {selected_animal} par commune"
                        )
                        st.plotly_chart(fig1, use_container_width=True)
                    
                    if len(compare_animals) > 1:
                        # Graphique de comparaison
                        compare_data = []
                        for animal in compare_animals:
                            total = df_anim[animal].sum()
                            compare_data.append({
                                'Type': animal,
                                'Effectif total': total
                            })
                        
                        compare_df = pd.DataFrame(compare_data)
                        fig2 = px.bar(
                            compare_df,
                            x='Type',
                            y='Effectif total',
                            title='Comparaison des effectifs animaux'
                        )
                        st.plotly_chart(fig2, use_container_width=True)
        
        else:
            st.info("Données de production animale non disponibles")
    
    with tab3:
        st.markdown("### 💧 ANALYSE DE L'IRRIGATION")
        
        if "L'IRRIGATION" in data_dict:
            df_irrig = data_dict["L'IRRIGATION"]
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # Sélection des données d'irrigation
                irrig_cols = [c for c in df_irrig.columns if any(x in c for x in ['irrigation', 'Sources', 'Oueds', 'Puits'])]
                
                if irrig_cols:
                    selected_col = st.selectbox(
                        "Source d'irrigation",
                        irrig_cols
                    )
                    
                    # Analyse des périmètres
                    if 'Périmètre_nbr' in df_irrig.columns:
                        st.metric("Nombre total de périmètres", f"{df_irrig['Périmètre_nbr'].sum():,.0f}")
            
            with col2:
                if 'selected_col' in locals():
                    # Carte thermique des communes
                    pivot_data = []
                    for idx, row in df_irrig.iterrows():
                        commune = row['Commune']
                        for col in irrig_cols:
                            if col in row:
                                pivot_data.append({
                                    'Commune': commune,
                                    'Source': col,
                                    'Valeur': row[col]
                                })
                    
                    if pivot_data:
                        pivot_df = pd.DataFrame(pivot_data)
                        pivot_table = pivot_df.pivot_table(
                            index='Commune',
                            columns='Source',
                            values='Valeur',
                            aggfunc='sum'
                        ).fillna(0)
                        
                        fig = px.imshow(
                            pivot_table,
                            title="Carte thermique des sources d'irrigation par commune",
                            color_continuous_scale="Blues"
                        )
                        st.plotly_chart(fig, use_container_width=True)
        
        else:
            st.info("Données d'irrigation non disponibles")

# --- PAGE : ANALYSE SECTORIELLE ---
elif page == "🔍 Analyse Sectorielle":
    st.markdown('<div class="main-header">🔍 Analyse Sectorielle Avancée</div>', unsafe_allow_html=True)
    
    sectors = {
        "🌾 Céréales et Légumineuses": ["PRODUCTION VEGETALE Céréales", "Légumineuses"],
        "🥦 Maraîchage": ["Maraîchage 1", "Maraichage 2", "Maraichage 3"],
        "🌳 Arboriculture": ["Plantation fruitière 1", "Plantation fruitière 2"],
        "🐄 Élevage": ["PRODUCTION ANIMALE", "APICULTURE", "AVICULTURE"],
        "💧 Irrigation": ["L'IRRIGATION"],
        "🏭 Agro-industrie": ["AGRO - INDUSTRIE", "COOPERATIVES"]
    }
    
    selected_sector = st.selectbox(
        "Sélectionnez un secteur à analyser",
        list(sectors.keys())
    )
    
    if selected_sector:
        sector_sheets = sectors[selected_sector]
        available_sheets = [s for s in sector_sheets if s in data_dict]
        
        if available_sheets:
            st.markdown(f"### {selected_sector}")
            
            # Analyse comparative des communes dans ce secteur
            all_commune_data = []
            
            for sheet in available_sheets:
                df = data_dict[sheet]
                if 'Commune' in df.columns:
                    numeric_cols = df.select_dtypes(include=[np.number]).columns
                    
                    for commune in df['Commune'].unique():
                        commune_df = df[df['Commune'] == commune]
                        commune_data = {'Commune': commune, 'Feuille': sheet}
                        
                        for col in numeric_cols:
                            if col != 'Commune':
                                commune_data[col] = commune_df[col].sum()
                        
                        all_commune_data.append(commune_data)
            
            if all_commune_data:
                analysis_df = pd.DataFrame(all_commune_data)
                
                # Regroupement par commune
                commune_summary = analysis_df.groupby('Commune').sum().reset_index()
                
                # Calcul des scores de performance
                score_cols = [c for c in commune_summary.columns if c != 'Commune']
                if score_cols:
                    # Normalisation et calcul du score
                    for col in score_cols:
                        if commune_summary[col].max() > 0:
                            commune_summary[f'{col}_normalized'] = (
                                commune_summary[col] / commune_summary[col].max()
                            )
                    
                    norm_cols = [c for c in commune_summary.columns if 'normalized' in c]
                    commune_summary['score_sectoriel'] = commune_summary[norm_cols].sum(axis=1)
                    
                    # Affichage du classement
                    st.markdown("#### 🏆 Classement des Communes")
                    
                    top_communes = commune_summary.sort_values('score_sectoriel', ascending=False).head(10)
                    
                    fig = px.bar(
                        top_communes,
                        x='Commune',
                        y='score_sectoriel',
                        color='score_sectoriel',
                        color_continuous_scale="greens",
                        title="Top 10 communes dans ce secteur"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Détails par commune
                    selected_commune = st.selectbox(
                        "Voir les détails d'une commune",
                        commune_summary['Commune'].unique()
                    )
                    
                    if selected_commune:
                        commune_details = analysis_df[analysis_df['Commune'] == selected_commune]
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown(f"##### 📊 Données pour {selected_commune}")
                            st.dataframe(
                                commune_details.drop(columns=['Commune']),
                                use_container_width=True
                            )
                        
                        with col2:
                            # Graphique radar pour la commune
                            if len(score_cols) > 2:
                                radar_data = []
                                for col in score_cols[:6]:  # Limiter à 6 variables
                                    value = commune_details[col].sum()
                                    radar_data.append({
                                        'Variable': col,
                                        'Valeur': value
                                    })
                                
                                radar_df = pd.DataFrame(radar_data)
                                
                                fig = px.line_polar(
                                    radar_df,
                                    r='Valeur',
                                    theta='Variable',
                                    line_close=True,
                                    title=f"Profil de {selected_commune}"
                                )
                                st.plotly_chart(fig, use_container_width=True)

# --- PAGE : ASSISTANT IA ---
elif page == "🤖 Assistant IA":
    st.markdown('<div class="main-header">🤖 Assistant IA Décisionnel</div>', unsafe_allow_html=True)
    
    if "gemini_api_key" not in st.secrets:
        st.error("⚠️ Clé API Gemini manquante. Veuillez la configurer dans les secrets.")
        st.stop()
    
    # Configuration de l'IA
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Interface
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### 📋 Contexte d'Analyse")
        
        # Catégories pour l'IA
        ia_categories = {
            "Superficies et Sols": ['REPARTITION DES SUPERFICIES', 'PEDOLOGIE 1', 'PEDOLOGIE 2'],
            "Production Végétale": ['PRODUCTION VEGETALE Céréales', 'Légumineuses', 'Maraîchage 1'],
            "Production Animale": ['PRODUCTION ANIMALE', 'APICULTURE'],
            "Irrigation": ["L'IRRIGATION"],
            "Analyse Complète": list(data_dict.keys())[:5]  # Limiter à 5 feuilles pour analyse complète
        }
        
        selected_category = st.selectbox(
            "Domaine d'analyse",
            list(ia_categories.keys())
        )
        
        # Suggestions de questions spécifiques
        st.markdown("### 💡 Questions suggérées")
        
        suggestions = {
            "Superficies et Sols": [
                "Quelles sont les communes avec la plus grande superficie agricole utile?",
                "Analyse la répartition des types de sols et son impact sur l'agriculture"
            ],
            "Production Végétale": [
                "Quelles communes ont les meilleurs rendements céréaliers?",
                "Propose des rotations de cultures optimisées"
            ],
            "Production Animale": [
                "Analyse la densité du cheptel par rapport à la superficie",
                "Quelles opportunités pour l'élevage?"
            ],
            "Irrigation": [
                "Évalue le potentiel d'extension des surfaces irriguées",
                "Analyse l'efficacité des différentes sources d'irrigation"
            ],
            "Analyse Complète": [
                "Donne un diagnostic global de l'agriculture à Chefchaouen",
                "Propose un plan de développement agricole"
            ]
        }
        
        for suggestion in suggestions.get(selected_category, []):
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
                    # Préparation du contexte avec les feuilles sélectionnées
                    selected_sheets = ia_categories[selected_category]
                    context_data = ""
                    
                    for sheet in selected_sheets:
                        if sheet in data_dict:
                            df = data_dict[sheet]
                            csv_sample = df.head(10).to_csv(index=False)
                            context_data += f"\n\n=== {sheet} ===\n{csv_sample}"
                    
                    prompt = f"""
                    Tu es un expert agronome spécialiste de la province de Chefchaouen au Maroc.
                    
                    CONTEXTE:
                    - Province: Chefchaouen
                    - Année de référence: 2012
                    - Type de données: Monographie agricole complète
                    - Domaine analysé: {selected_category}
                    
                    DONNÉES DISPONIBLES (échantillon):
                    {context_data[:4000]}
                    
                    INSTRUCTIONS SPÉCIFIQUES:
                    1. Analyse en tant qu'expert du développement rural
                    2. Sois concret et propose des recommandations actionnables
                    3. Fais référence aux communes spécifiques de Chefchaouen
                    4. Intègre les particularités montagneuses de la région
                    5. Propose des solutions adaptées au contexte local
                    6. Structure ta réponse avec des sections claires
                    
                    QUESTION DE L'UTILISATEUR: {question}
                    
                    RÉPONSE (en français, format professionnel):
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
    st.markdown('<div class="main-header">📈 Rapports Agricoles Complets</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["📋 Rapport Global", "🏘️ Par Commune", "🌾 Par Culture"])
    
    with tab1:
        st.markdown("### 📊 Rapport Agricole Global")
        
        # Sélection des données à inclure
        st.markdown("#### Sélection des Données")
        
        categories = list(set(sheet_categories.values()))
        selected_categories = st.multiselect(
            "Catégories à inclure dans le rapport",
            categories,
            default=categories[:3]
        )
        
        # Filtrage des feuilles par catégorie
        selected_sheets = []
        for sheet, cat in sheet_categories.items():
            if cat in selected_categories:
                selected_sheets.append(sheet)
        
        if st.button("📥 Générer le Rapport Complet", type="primary"):
            with st.spinner("Génération du rapport en cours..."):
                # Création du rapport
                report = create_agricultural_report(data_dict, selected_sheets)
                
                # Affichage du rapport
                st.markdown("---")
                st.markdown(report)
                
                # Ajout de visualisations
                st.markdown("## 📊 Visualisations du Rapport")
                
                # Graphique synthétique
                if 'REPARTITION DES SUPERFICIES' in selected_sheets:
                    df_sup = data_dict['REPARTITION DES SUPERFICIES']
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Diagramme circulaire des superficies
                        if 'S.AU_Total' in df_sup.columns:
                            sau = df_sup['S.AU_Total'].sum()
                            non_sau = df_sup['Sup.Totale'].sum() - sau
                            
                            fig = px.pie(
                                values=[sau, non_sau],
                                names=['SAU', 'Autres terres'],
                                title='Répartition SAU / Autres terres'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # Top 10 des communes par SAU
                        if 'S.AU_Total' in df_sup.columns:
                            top_sau = df_sup.nlargest(10, 'S.AU_Total')[['Commune', 'S.AU_Total']]
                            fig = px.bar(
                                top_sau,
                                x='Commune',
                                y='S.AU_Total',
                                title='Top 10 communes par SAU'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                
                # Téléchargement
                st.download_button(
                    label="📄 Télécharger le Rapport (TXT)",
                    data=report,
                    file_name=f"rapport_agricole_chefchaouen_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
    
    with tab2:
        st.markdown("### 🏘️ Rapport Par Commune")
        
        # Sélection d'une commune
        communes_list = []
        for df in data_dict.values():
            if 'Commune' in df.columns:
                communes_list.extend(df['Commune'].dropna().unique().tolist())
        
        communes_list = sorted(list(set(communes_list)))
        
        selected_commune = st.selectbox(
            "Sélectionnez une commune",
            communes_list
        )
        
        if selected_commune and st.button("📊 Générer le Rapport Communal"):
            with st.spinner("Analyse de la commune en cours..."):
                # Collecte des données pour la commune sélectionnée
                commune_data = []
                
                for sheet_name, df in data_dict.items():
                    if 'Commune' in df.columns:
                        commune_rows = df[df['Commune'] == selected_commune]
                        if not commune_rows.empty:
                            for _, row in commune_rows.iterrows():
                                for col in df.columns:
                                    if col != 'Commune' and pd.api.types.is_numeric_dtype(df[col]):
                                        commune_data.append({
                                            'Feuille': sheet_name,
                                            'Variable': col,
                                            'Valeur': row[col]
                                        })
                
                if commune_data:
                    commune_df = pd.DataFrame(commune_data)
                    
                    st.markdown(f"## 📋 Rapport pour {selected_commune}")
                    
                    # Vue synthétique
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Nombre de données", len(commune_df))
                    
                    with col2:
                        st.metric("Catégories", commune_df['Feuille'].nunique())
                    
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
                    fig = px.bar(
                        top_values,
                        x='Variable',
                        y='Valeur',
                        color='Feuille',
                        title=f"Top 10 indicateurs - {selected_commune}"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(f"Aucune donnée trouvée pour la commune {selected_commune}")

# --- PAGE : CARTOGRAPHIE ---
elif page == "🗺️ Cartographie":
    st.markdown('<div class="main-header">🗺️ Visualisation Géographique</div>', unsafe_allow_html=True)
    
    st.info("""
    🗺️ **Module de cartographie agricole**
    
    Cette fonctionnalité permet de visualiser spatialement les données agricoles.
    Pour une implémentation complète, vous aurez besoin:
    1. Des coordonnées GPS des communes
    2. D'une API cartographique (Google Maps, Leaflet, etc.)
    3. D'une clé API pour les services cartographiques
    
    Voici un aperçu de ce qui est possible:
    """)
    
    # Simulation de données géographiques
    communes_geo = {
        'Bab Taza': {'lat': 34.98, 'lon': -5.27},
        'Bni Saleh': {'lat': 35.02, 'lon': -5.15},
        'Bni Darkoul': {'lat': 35.05, 'lon': -5.12},
        'Fifi': {'lat': 34.95, 'lon': -5.20},
        'Bni Faghloun': {'lat': 35.08, 'lon': -5.10}
    }
    
    # Création d'un DataFrame géographique simulé
    geo_data = []
    for commune, coords in communes_geo.items():
        # Recherche des données pour cette commune
        superficie = 0
        if 'REPARTITION DES SUPERFICIES' in data_dict:
            df_sup = data_dict['REPARTITION DES SUPERFICIES']
            commune_data = df_sup[df_sup['Commune'] == commune]
            if not commune_data.empty and 'Sup.Totale' in df_sup.columns:
                superficie = commune_data['Sup.Totale'].iloc[0]
        
        geo_data.append({
            'Commune': commune,
            'Latitude': coords['lat'],
            'Longitude': coords['lon'],
            'Superficie': superficie,
            'Taille_point': min(50, superficie / 1000) if superficie > 0 else 10
        })
    
    if geo_data:
        geo_df = pd.DataFrame(geo_data)
        
        # Carte simulée avec Plotly
        fig = px.scatter_mapbox(
            geo_df,
            lat="Latitude",
            lon="Longitude",
            size="Taille_point",
            color="Superficie",
            hover_name="Commune",
            hover_data=["Superficie"],
            color_continuous_scale=px.colors.sequential.Viridis,
            size_max=30,
            zoom=9,
            height=600,
            title="Répartition des superficies par commune (simulation)"
        )
        
        fig.update_layout(mapbox_style="open-street-map")
        fig.update_layout(margin={"r":0,"t":50,"l":0,"b":0})
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Légende et explications
        with st.expander("ℹ️ Comment utiliser la cartographie"):
            st.markdown("""
            ### Pour implémenter une cartographie complète:
            
            1. **Obtenir les coordonnées GPS** des 27 communes de Chefchaouen
            2. **Configurer une API cartographique** (OpenStreetMap, Google Maps, Mapbox)
            3. **Associer les données agricoles** aux coordonnées géographiques
            4. **Créer des couches thématiques** par type de données
            
            ### Applications possibles:
            - Visualisation des superficies par culture
            - Cartographie des zones irriguées
            - Analyse de la densité du cheptel
            - Planification des infrastructures agricoles
            """)

# --- PAGE : PARAMÈTRES ---
else:
    st.markdown('<div class="main-header">⚙️ Paramètres et Administration</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["🔧 Configuration", "📊 Gestion des Données", "📚 Documentation"])
    
    with tab1:
        st.markdown("### Configuration de l'Application")
        
        # Informations système
        st.markdown("#### Informations Système")
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.info(f"**Version:** 3.0.0 (Spécial Chefchaouen)")
            st.info(f"**Feuilles chargées:** {len(data_dict)}")
            st.info(f"**Communes détectées:** {len(set().union(*[df['Commune'].unique() for df in data_dict.values() if 'Commune' in df.columns]))}")
        
        with info_col2:
            st.info(f"**Dernière actualisation:** {datetime.now().strftime('%H:%M:%S')}")
            st.info(f"**Catégories disponibles:** {len(set(sheet_categories.values()))}")
            st.info(f"**ID Google Sheet:** {SHEET_ID[:20]}...")
        
        # Paramètres d'affichage
        st.markdown("#### Personnalisation")
        
        col1, col2 = st.columns(2)
        
        with col1:
            theme = st.selectbox(
                "Thème de couleur",
                ["Vert Agricole (Par défaut)", "Bleu Marin", "Terre Cuite", "Classique"]
            )
        
        with col2:
            language = st.selectbox(
                "Langue d'interface",
                ["Français", "Arabe", "Anglais", "Espagnol"]
            )
        
        if st.button("💾 Enregistrer les Préférences", type="primary"):
            st.success("Préférences enregistrées avec succès!")
            st.balloons()
    
    with tab2:
        st.markdown("### Gestion et Export des Données")
        
        # Vue d'ensemble structurée
        st.markdown("#### Vue d'Ensemble des Données")
        
        overview_data = []
        for sheet, cat in sheet_categories.items():
            df = data_dict[sheet]
            overview_data.append({
                'Feuille': sheet,
                'Catégorie': cat,
                'Lignes': len(df),
                'Colonnes': len(df.columns),
                'Communes': df['Commune'].nunique() if 'Commune' in df.columns else 0
            })
        
        overview_df = pd.DataFrame(overview_data)
        st.dataframe(overview_df, use_container_width=True)
        
        # Export des données
        st.markdown("#### Export des Données")
        
        export_col1, export_col2 = st.columns(2)
        
        with export_col1:
            export_sheet = st.selectbox(
                "Sélectionner une feuille à exporter",
                list(data_dict.keys())
            )
            
            if export_sheet:
                df = data_dict[export_sheet]
                
                # Options d'export
                export_format = st.radio(
                    "Format d'export",
                    ["CSV", "Excel", "JSON"]
                )
        
        with export_col2:
            if export_sheet:
                st.markdown("##### Aperçu des données")
                st.dataframe(df.head(), use_container_width=True)
        
        # Boutons d'export
        if export_sheet:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📥 Télécharger CSV", use_container_width=True):
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="✅ Cliquez pour télécharger",
                        data=csv,
                        file_name=f"{export_sheet}.csv",
                        mime="text/csv",
                        key="csv_download"
                    )
            
            with col2:
                if st.button("📊 Télécharger Excel", use_container_width=True):
                    # Conversion en Excel
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Données')
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="✅ Cliquez pour télécharger",
                        data=excel_data,
                        file_name=f"{export_sheet}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="excel_download"
                    )
            
            with col3:
                if st.button("📄 Télécharger JSON", use_container_width=True):
                    json_str = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="✅ Cliquez pour télécharger",
                        data=json_str,
                        file_name=f"{export_sheet}.json",
                        mime="application/json",
                        key="json_download"
                    )
    
    with tab3:
        st.markdown("### 📚 Guide d'Utilisation Complet")
        
        with st.expander("🎯 Présentation de l'Application"):
            st.markdown("""
            ## Agri-Analytics Chefchaouen
            
            **Objectif:** Fournir une plateforme complète d'analyse des données agricoles de la province de Chefchaouen.
            
            **Données disponibles:** Monographie agricale 2012 avec 27+ feuilles couvrant:
            - Superficies et occupation des sols
            - Production végétale (céréales, légumineuses, maraîchage)
            - Production animale et apiculture
            - Irrigation et ressources en eau
            - Données pédologiques et climatiques
            - Population et organisations professionnelles
            """)
        
        with st.expander("📊 Comment analyser les données"):
            st.markdown("""
            ### Méthodologie d'analyse:
            
            1. **Tableau de Bord:** Vue d'ensemble avec les indicateurs clés
            2. **Visualisations:** Graphiques interactifs par secteur
            3. **Analyse Sectorielle:** Approche approfondie par domaine agricole
            4. **Assistant IA:** Analyse intelligente avec recommandations
            5. **Rapports:** Génération de documents d'analyse
            6. **Cartographie:** Visualisation spatiale (à développer)
            
            ### Conseils pour l'analyse:
            - Comparez plusieurs communes pour identifier les meilleures pratiques
            - Utilisez l'Assistant IA pour des insights rapides
            - Exportez les rapports pour le partage avec les décideurs
            - Croisez les données (ex: irrigation × production)
            """)
        
        with st.expander("🤖 Utilisation de l'Assistant IA"):
            st.markdown("""
            ### Guide pour l'Assistant IA:
            
            **Types de questions recommandées:**
            - Questions comparatives: "Quelles communes ont les meilleurs rendements?"
            - Questions d'optimisation: "Comment améliorer la productivité?"
            - Questions stratégiques: "Quels investissements prioritaires?"
            - Questions techniques: "Quelles cultures adaptées au sol?"
            
            **Exemples de questions efficaces:**
            1. "Analyse les données d'irrigation et propose un plan d'amélioration"
            2. "Compare la production céréalière entre les communes du nord et du sud"
            3. "Identifie les opportunités pour développer l'apiculture"
            4. "Propose un plan de rotation des cultures pour Bab Taza"
            """)
        
        st.markdown("### 📞 Support et Contact")
        st.markdown("""
        Pour toute question, problème ou suggestion:
        
        **Support technique:** [email ou contact à ajouter]
        **Documentation:** [lien vers documentation détaillée]
        **Formations:** [informations sur les sessions de formation]
        
        *Version 3.0 - Spécial Chefchaouen 2012*
        """)