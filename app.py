import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re
from datetime import datetime
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
    .answer-box {
        background-color: #e8f5e9;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #4caf50;
    }
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---
def clean_val(val):
    """Nettoyage robuste des valeurs numériques"""
    if pd.isna(val) or val in ["", None]:
        return 0.0
    s = str(val).strip()
    s = re.sub(r'[\s\xa0,]+', '', s)
    match = re.search(r"[-+]?\d*\.?\d+", s)
    return float(match.group()) if match else 0.0

# --- FONCTIONS D'ANALYSE INTELLIGENTE ---
class AgriAnalyst:
    """Classe pour analyser intelligemment les données agricoles"""
    
    def __init__(self, data_dict):
        self.data_dict = data_dict
        self.cache = {}
    
    def find_crop_data(self, crop_name):
        """Trouve les données pour une culture spécifique"""
        crop_name_lower = crop_name.lower()
        results = []
        
        for sheet_name, df in self.data_dict.items():
            for col in df.columns:
                col_lower = str(col).lower()
                
                # Chercher la culture dans le nom de colonne
                if crop_name_lower in col_lower:
                    # Vérifier si c'est une colonne de surface
                    if any(keyword in col_lower for keyword in ['sup', 'surface', 'ha', 'superficie']):
                        for _, row in df.iterrows():
                            commune = row.get('Commune', 'Inconnue')
                            value = row[col]
                            if pd.notna(value) and value > 0:
                                results.append({
                                    'feuille': sheet_name,
                                    'colonne': col,
                                    'commune': commune,
                                    'valeur': value,
                                    'type': 'surface'
                                })
                    
                    # Chercher aussi les rendements
                    elif any(keyword in col_lower for keyword in ['rdt', 'rendement', 'qx', 'production']):
                        for _, row in df.iterrows():
                            commune = row.get('Commune', 'Inconnue')
                            value = row[col]
                            if pd.notna(value) and value > 0:
                                results.append({
                                    'feuille': sheet_name,
                                    'colonne': col,
                                    'commune': commune,
                                    'valeur': value,
                                    'type': 'rendement'
                                })
        
        return results
    
    def analyze_crop(self, crop_name):
        """Analyse complète d'une culture"""
        crop_data = self.find_crop_data(crop_name)
        
        if not crop_data:
            return None
        
        df = pd.DataFrame(crop_data)
        
        # Séparer surfaces et rendements
        surfaces = df[df['type'] == 'surface']
        rendements = df[df['type'] == 'rendement']
        
        analysis = {
            'crop': crop_name,
            'total_communes': df['commune'].nunique(),
            'total_surface': surfaces['valeur'].sum() if not surfaces.empty else 0,
            'communes_avec_surface': [],
            'top_communes_surface': [],
            'top_communes_rendement': []
        }
        
        # Top communes par surface
        if not surfaces.empty:
            surface_by_commune = surfaces.groupby('commune')['valeur'].sum().reset_index()
            surface_by_commune = surface_by_commune.sort_values('valeur', ascending=False)
            analysis['top_communes_surface'] = surface_by_commune.head(5).to_dict('records')
            analysis['communes_avec_surface'] = surface_by_commune['commune'].tolist()
        
        # Top communes par rendement
        if not rendements.empty:
            rendement_by_commune = rendements.groupby('commune')['valeur'].mean().reset_index()
            rendement_by_commune = rendement_by_commune.sort_values('valeur', ascending=False)
            analysis['top_communes_rendement'] = rendement_by_commune.head(5).to_dict('records')
        
        return analysis
    
    def answer_question(self, question):
        """Répond intelligemment à une question"""
        question_lower = question.lower()
        
        # Détection de la culture demandée
        crops_keywords = {
            'tomate': ['tomate', 'tomates'],
            'pomme de terre': ['pomme de terre', 'patate', 'pdt'],
            'blé': ['blé', 'ble', 'céréale'],
            'orge': ['orge'],
            'maïs': ['maïs', 'mais'],
            'olivier': ['olivier', 'olive'],
            'figuier': ['figuier', 'figue'],
            'amandier': ['amandier', 'amande'],
            'vigne': ['vigne', 'raisin'],
            'fève': ['fève', 'fève'],
            'pois': ['pois'],
            'lentille': ['lentille'],
            'carotte': ['carotte'],
            'oignon': ['oignon'],
            'ail': ['ail']
        }
        
        detected_crop = None
        for crop, keywords in crops_keywords.items():
            if any(keyword in question_lower for keyword in keywords):
                detected_crop = crop
                break
        
        if detected_crop:
            # Analyser cette culture
            analysis = self.analyze_crop(detected_crop)
            
            if analysis:
                # Construire la réponse
                response = self._build_crop_response(analysis, question)
                return response
            else:
                return self._build_no_data_response(detected_crop)
        
        # Questions générales
        if any(word in question_lower for word in ['meilleur', 'plus grand', 'maximum', 'top']):
            if 'superficie' in question_lower or 'surface' in question_lower:
                return self._answer_biggest_area(question)
        
        # Réponse par défaut
        return self._build_general_response(question)
    
    def _build_crop_response(self, analysis, question):
        """Construit une réponse pour une culture spécifique"""
        crop = analysis['crop']
        
        if analysis['top_communes_surface']:
            top_commune = analysis['top_communes_surface'][0]
            
            response = f"""
            <div class='answer-box'>
            <h3>🍅 Analyse pour les {crop}s à Chefchaouen</h3>
            
            <h4>🥇 Commune avec la plus grande superficie:</h4>
            <p><strong>{top_commune['commune']}</strong> avec <strong>{top_commune['valeur']} hectares</strong> de {crop}s</p>
            
            <h4>📊 Classement complet:</h4>
            <ol>
            """
            
            for i, commune_data in enumerate(analysis['top_communes_surface'][:5], 1):
                response += f"<li><strong>{commune_data['commune']}</strong>: {commune_data['valeur']} ha</li>\n"
            
            response += f"""
            </ol>
            
            <h4>📈 Statistiques:</h4>
            <ul>
            <li><strong>Superficie totale</strong>: {analysis['total_surface']} hectares</li>
            <li><strong>Communes cultivant des {crop}s</strong>: {analysis['total_communes']}</li>
            </ul>
            
            <h4>🎯 Recommandations:</h4>
            <p>Pour développer la culture des {crop}s, commencez par <strong>{top_commune['commune']}</strong> où l'expérience existe déjà. 
            Ensuite, étendez aux communes suivantes du classement.</p>
            </div>
            """
            
            # Ajouter un graphique
            if len(analysis['top_communes_surface']) > 1:
                fig = self._create_crop_chart(analysis, crop)
                return response, fig
            
            return response, None
        
        else:
            return self._build_no_data_response(crop), None
    
    def _create_crop_chart(self, analysis, crop):
        """Crée un graphique pour la culture"""
        df = pd.DataFrame(analysis['top_communes_surface'])
        
        fig = px.bar(
            df,
            x='commune',
            y='valeur',
            title=f"Top communes pour les {crop}s (superficie en ha)",
            color='valeur',
            color_continuous_scale="greens",
            text='valeur'
        )
        fig.update_traces(texttemplate='%{text} ha', textposition='outside')
        fig.update_layout(xaxis_tickangle=-45)
        
        return fig
    
    def _answer_biggest_area(self, question):
        """Répond aux questions sur les plus grandes superficies"""
        all_surfaces = []
        
        for sheet_name, df in self.data_dict.items():
            for col in df.columns:
                col_lower = str(col).lower()
                if any(keyword in col_lower for keyword in ['sup', 'surface', 'ha', 'superficie']):
                    for _, row in df.iterrows():
                        commune = row.get('Commune', 'Inconnue')
                        value = row[col]
                        if pd.notna(value) and value > 0 and commune != 'Inconnue':
                            # Extraire le nom de la culture du nom de colonne
                            col_parts = col.split('-')
                            if len(col_parts) > 1:
                                culture = col_parts[0].strip()
                            else:
                                culture = "Culture diverse"
                            
                            all_surfaces.append({
                                'commune': commune,
                                'culture': culture,
                                'surface': value,
                                'feuille': sheet_name
                            })
        
        if all_surfaces:
            df_all = pd.DataFrame(all_surfaces)
            
            # Plus grande superficie totale par commune
            commune_totals = df_all.groupby('commune')['surface'].sum().reset_index()
            commune_totals = commune_totals.sort_values('surface', ascending=False)
            
            top_commune = commune_totals.iloc[0]
            
            response = f"""
            <div class='answer-box'>
            <h3>🏆 Communes avec les plus grandes superficies agricoles</h3>
            
            <h4>🥇 Commune avec la plus grande superficie agricole totale:</h4>
            <p><strong>{top_commune['commune']}</strong> avec <strong>{top_commune['surface']:.1f} hectares</strong> au total</p>
            
            <h4>📊 Top 5 des communes par superficie totale:</h4>
            <ol>
            """
            
            for i, row in commune_totals.head(5).iterrows():
                response += f"<li><strong>{row['commune']}</strong>: {row['surface']:.1f} ha</li>\n"
            
            response += """
            </ol>
            
            <h4>🔍 Détails par culture:</h4>
            <p>Pour connaître la commune avec la plus grande superficie pour une culture spécifique (tomates, pommes de terre, etc.), 
            posez une question précise comme "Quelle commune a la plus grande superficie de tomates?"</p>
            </div>
            """
            
            return response, None
        
        return "Je n'ai pas trouvé de données de superficie dans les feuilles chargées.", None
    
    def _build_no_data_response(self, crop):
        """Construit une réponse quand il n'y a pas de données"""
        return f"""
        <div class='answer-box'>
        <h3>🔍 Analyse pour les {crop}s</h3>
        
        <p>Je n'ai pas trouvé de données spécifiques pour les <strong>{crop}s</strong> dans les feuilles chargées.</p>
        
        <h4>🎯 Suggestions:</h4>
        <ol>
        <li>Vérifiez si les données sont dans les feuilles "Maraîchage 1", "Maraichage 2" ou "Maraichage 3"</li>
        <li>Consultez la page "📊 Exploration Données" pour voir toutes les feuilles disponibles</li>
        <li>Essayez avec d'autres cultures comme: tomates, blé, orge, oliviers</li>
        </ol>
        
        <h4>📋 Feuilles disponibles contenant "pomme":</h4>
        <ul>
        """
        
        # Chercher les feuilles qui pourraient contenir des données sur cette culture
        for sheet_name in self.data_dict.keys():
            if 'maraichage' in sheet_name.lower() or 'maraîchage' in sheet_name.lower():
                response += f"<li>{sheet_name}</li>\n"
        
        response += "</ul></div>"
        
        return response
    
    def _build_general_response(self, question):
        """Construit une réponse générale"""
        return f"""
        <div class='answer-box'>
        <h3>🤖 Analyse Intelligente</h3>
        
        <p>J'ai analysé votre question: <strong>"{question}"</strong></p>
        
        <h4>🎯 Pour une réponse précise:</h4>
        <ol>
        <li><strong>Spécifiez la culture</strong>: "tomates", "pommes de terre", "blé", etc.</li>
        <li><strong>Posez des questions précises</strong>:
            <ul>
            <li>"Quelle commune a la plus grande superficie de tomates?"</li>
            <li>"Quels sont les meilleurs rendements en blé?"</li>
            <li>"Où développer l'irrigation pour les pommes de terre?"</li>
            </ul>
        </li>
        </ol>
        
        <h4>🌱 Cultures que je peux analyser:</h4>
        <ul>
        <li>Tomates, Pommes de terre, Carottes, Oignons, Ail</li>
        <li>Blé, Orge, Maïs, Avoine</li>
        <li>Oliviers, Figuiers, Amandiers, Vigne</li>
        <li>Fèves, Pois, Lentilles, Pois chiches</li>
        </ul>
        
        <p><strong>Exemple de question précise:</strong> "Quelle est la commune avec la plus grande superficie de tomates ?"</p>
        </div>
        """

# --- CHARGEMENT DES DONNÉES ---
@st.cache_data(ttl=600)
def load_data():
    """Charge les données depuis Google Sheets"""
    try:
        SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"
        
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Utilisation des secrets Streamlit
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=scope
        )
        
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_ID)
        
        all_data = {}
        
        for ws in sh.worksheets():
            try:
                raw = ws.get_all_values()
                
                if not raw:
                    continue
                
                # Chercher la ligne avec "Commune"
                header_idx = None
                for i, row in enumerate(raw[:10]):
                    row_lower = [str(cell).lower().strip() for cell in row]
                    if "commune" in row_lower:
                        header_idx = i
                        break
                
                if header_idx is None:
                    continue
                
                # Prendre les deux lignes comme en-têtes
                headers = raw[header_idx:header_idx+2]
                
                # Construire les noms de colonnes
                col_names = []
                max_cols = max(len(h) for h in headers)
                
                for i in range(max_cols):
                    main = headers[0][i] if i < len(headers[0]) else ""
                    sub = headers[1][i] if len(headers) > 1 and i < len(headers[1]) else ""
                    
                    main_str = str(main).strip()
                    sub_str = str(sub).strip()
                    
                    if main_str and sub_str and main_str != sub_str:
                        col_name = f"{main_str} - {sub_str}"
                    elif main_str:
                        col_name = main_str
                    elif sub_str:
                        col_name = sub_str
                    else:
                        col_name = f"Colonne_{i+1}"
                    
                    col_names.append(col_name)
                
                # Données
                data_start = header_idx + 2
                data_rows = raw[data_start:] if data_start < len(raw) else []
                
                # Créer le DataFrame
                df = pd.DataFrame(data_rows, columns=col_names)
                
                # Nettoyage
                for col in df.columns:
                    if 'commune' not in col.lower():
                        df[col] = df[col].apply(clean_val)
                
                # Nettoyer la colonne Commune
                if 'Commune' in df.columns:
                    df['Commune'] = df['Commune'].astype(str).str.strip()
                    df = df[~df['Commune'].str.contains('total|TOTAL|S/T|munici', case=False, na=False)]
                    df = df[df['Commune'] != '']
                
                all_data[ws.title] = df
                
            except Exception as e:
                continue
        
        return all_data
        
    except Exception as e:
        st.error(f"Erreur de chargement : {str(e)}")
        return {}

# --- INITIALISATION ---
# Initialisation de la session state
if 'page' not in st.session_state:
    st.session_state.page = "Accueil"
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'analyst' not in st.session_state:
    st.session_state.analyst = None

# Chargement des données
with st.spinner("🔄 Chargement des données agricoles..."):
    data_dict = load_data()
    
    if not data_dict:
        st.error("❌ Impossible de charger les données. Vérifiez la connexion.")
        st.stop()
    
    # Initialiser l'analyste
    if st.session_state.analyst is None:
        st.session_state.analyst = AgriAnalyst(data_dict)
    
    st.success(f"✅ {len(data_dict)} feuilles chargées!")

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="main-header">🌿 Navigation</div>', unsafe_allow_html=True)
    
    # Boutons de navigation
    if st.button("🏠 Accueil", use_container_width=True, type="primary"):
        st.session_state.page = "Accueil"
        st.rerun()
    
    if st.button("🤖 Assistant Agricole", use_container_width=True):
        st.session_state.page = "Assistant"
        st.rerun()
    
    if st.button("📊 Visualisations", use_container_width=True):
        st.session_state.page = "Viz"
        st.rerun()
    
    if st.button("🌱 Analyse Cultures", use_container_width=True):
        st.session_state.page = "Cultures"
        st.rerun()
    
    if st.button("📋 Exploration Données", use_container_width=True):
        st.session_state.page = "Donnees"
        st.rerun()
    
    st.divider()
    
    # Stats
    if data_dict:
        total_rows = sum(len(df) for df in data_dict.values())
        total_communes = set()
        for df in data_dict.values():
            if 'Commune' in df.columns:
                total_communes.update(df['Commune'].unique())
        
        st.metric("Feuilles de données", len(data_dict))
        st.metric("Communes", len(total_communes))
        st.metric("Lignes totales", f"{total_rows:,}")
    
    st.divider()
    
    if st.button("🔄 Actualiser données", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- PAGE ACCUEIL ---
if st.session_state.page == "Accueil":
    st.markdown('<div class="main-header">🌱 Agri-Analytics Chefchaouen</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 📊 Plateforme d'Analyse Agricole Intelligente
        
        **Capacités d'analyse:**
        - 🔍 **Recherche intelligente** par culture et commune
        - 📈 **Analyse comparative** des performances
        - 🎯 **Recommandations personnalisées**
        - 📊 **Visualisations interactives**
        
        **Exemples de questions:**
        1. "Quelle commune a la plus grande superficie de tomates?"
        2. "Où sont les meilleurs rendements en blé?"
        3. "Quelles communes cultivent des oliviers?"
        4. "Comparer les surfaces irriguées par commune"
        
        **🌿 Cultures analysables:**
        - Maraîchage: Tomates, Pommes de terre, Carottes, Oignons
        - Céréales: Blé, Orge, Maïs, Avoine
        - Arboriculture: Oliviers, Figuiers, Amandiers
        - Légumineuses: Fèves, Pois, Lentilles
        """)
    
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🚀 Questions rapides")
        
        quick_questions = [
            "🍅 Superficie de tomates?",
            "🥔 Meilleures pommes de terre?",
            "🌾 Top blé par commune?",
            "💧 Irrigation disponible?"
        ]
        
        for q in quick_questions:
            if st.button(q, use_container_width=True):
                st.session_state.page = "Assistant"
                if "tomate" in q.lower():
                    st.session_state.quick_question = "Quelle commune a la plus grande superficie de tomates?"
                elif "pomme" in q.lower():
                    st.session_state.quick_question = "Quelle commune a la plus grande superficie de pommes de terre?"
                elif "blé" in q.lower():
                    st.session_state.quick_question = "Quelle commune a la meilleure production de blé?"
                elif "irrigation" in q.lower():
                    st.session_state.quick_question = "Quelles communes ont le plus d'irrigation?"
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Aperçu des données
    st.divider()
    st.markdown("### 📋 Aperçu des données chargées")
    
    cols = st.columns(3)
    sheet_list = list(data_dict.keys())
    
    for i, sheet_name in enumerate(sheet_list[:6]):
        with cols[i % 3]:
            with st.expander(f"📄 {sheet_name[:20]}..."):
                df = data_dict[sheet_name]
                st.write(f"**{len(df)}** lignes, **{len(df.columns)}** colonnes")
                if 'Commune' in df.columns:
                    st.write(f"**{df['Commune'].nunique()}** communes")
                st.dataframe(df.head(3), use_container_width=True, height=150)

# --- PAGE ASSISTANT ---
elif st.session_state.page == "Assistant":
    st.markdown('<div class="main-header">🤖 Assistant Agricole Intelligent</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### 💬 Posez votre question en français naturel
    
    **Exemples:**
    - "Quelle commune a la plus grande superficie de tomates?"
    - "Où sont les meilleurs rendements en blé?"
    - "Quelles communes cultivent des pommes de terre?"
    - "Comparer l'irrigation entre Bab Taza et Tanaqob"
    """)
    
    # Saisie de la question
    col1, col2 = st.columns([3, 1])
    
    with col1:
        user_question = st.text_input(
            "Votre question:",
            placeholder="Ex: Quelle commune a la plus grande superficie de pommes de terre?",
            key="question_input"
        )
    
    with col2:
        analyze_btn = st.button("🔍 Analyser", use_container_width=True, type="primary")
    
    # Utiliser la question rapide si disponible
    if 'quick_question' in st.session_state:
        user_question = st.session_state.quick_question
        del st.session_state.quick_question
        analyze_btn = True
    
    if analyze_btn and user_question:
        # Ajouter à l'historique
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_question,
            "time": datetime.now().strftime("%H:%M")
        })
        
        # Analyser la question
        with st.spinner("🔍 Analyse des données en cours..."):
            response, chart = st.session_state.analyst.answer_question(user_question)
        
        # Ajouter la réponse à l'historique
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "time": datetime.now().strftime("%H:%M")
        })
    
    # Afficher l'historique
    st.markdown("---")
    st.markdown("### 📝 Historique des analyses")
    
    if not st.session_state.chat_history:
        st.info("👆 Posez votre première question ci-dessus pour commencer l'analyse!")
    else:
        for message in reversed(st.session_state.chat_history[-5:]):  # Afficher les 5 derniers
            with st.container():
                if message["role"] == "user":
                    st.markdown(f"""
                    <div style='background-color: #e3f2fd; padding: 15px; border-radius: 10px; margin: 10px 0;'>
                    <strong>👤 Vous ({message['time']}):</strong><br>
                    {message['content']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(message['content'], unsafe_allow_html=True)
                    
                    # Afficher le graphique si disponible
                    if 'chart' in locals() and chart is not None:
                        st.plotly_chart(chart, use_container_width=True)
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", use_container_width=True):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE ANALYSE CULTURES ---
elif st.session_state.page == "Cultures":
    st.markdown('<div class="main-header">🌱 Analyse par Culture</div>', unsafe_allow_html=True)
    
    # Sélection de la culture
    col1, col2 = st.columns([2, 1])
    
    with col1:
        crop_options = [
            "Tomates",
            "Pommes de terre",
            "Blé",
            "Orge",
            "Maïs",
            "Oliviers",
            "Figuiers",
            "Amandiers",
            "Vigne",
            "Fèves",
            "Pois",
            "Lentilles",
            "Carottes",
            "Oignons",
            "Ail"
        ]
        
        selected_crop = st.selectbox(
            "Sélectionnez une culture à analyser:",
            crop_options
        )
    
    with col2:
        analyze_crop = st.button("📊 Analyser cette culture", use_container_width=True, type="primary")
    
    if analyze_crop:
        with st.spinner(f"🔍 Analyse des {selected_crop} en cours..."):
            analysis = st.session_state.analyst.analyze_crop(selected_crop.lower())
        
        if analysis:
            # Afficher les résultats
            st.markdown(f'<div class="answer-box"><h3>📈 Analyse pour les {selected_crop}</h3>', unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Superficie totale", f"{analysis['total_surface']:.1f} ha")
            
            with col2:
                st.metric("Communes", analysis['total_communes'])
            
            with col3:
                if analysis['top_communes_surface']:
                    top = analysis['top_communes_surface'][0]
                    st.metric("Meilleure commune", top['commune'])
            
            # Top communes
            if analysis['top_communes_surface']:
                st.markdown("### 🏆 Top des communes par superficie")
                
                df_top = pd.DataFrame(analysis['top_communes_surface'])
                fig = px.bar(
                    df_top,
                    x='commune',
                    y='valeur',
                    title=f"Superficie de {selected_crop} par commune",
                    color='valeur',
                    color_continuous_scale="greens",
                    text='valeur'
                )
                fig.update_traces(texttemplate='%{text} ha', textposition='outside')
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                
                # Tableau détaillé
                st.dataframe(df_top, use_container_width=True)
            else:
                st.info(f"Aucune donnée de superficie trouvée pour les {selected_crop}")
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning(f"Aucune donnée trouvée pour les {selected_crop}")
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_cultures"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE VISUALISATIONS ---
elif st.session_state.page == "Viz":
    st.markdown('<div class="main-header">📊 Visualisations Interactives</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible")
        st.stop()
    
    # Sélection de la feuille
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille:",
        list(data_dict.keys())
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        # Colonnes disponibles
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if numeric_cols:
            col1, col2 = st.columns([1, 3])
            
            with col1:
                selected_col = st.selectbox("Variable:", numeric_cols)
                chart_type = st.selectbox("Type:", ["Barres", "Camembert", "Histogramme"])
                top_n = st.slider("Nombre:", 5, 30, 15)
            
            with col2:
                # Préparer les données
                if 'Commune' in df.columns:
                    plot_data = df[['Commune', selected_col]].dropna()
                    plot_data = plot_data.sort_values(selected_col, ascending=False).head(top_n)
                    
                    if chart_type == "Barres":
                        fig = px.bar(
                            plot_data,
                            x='Commune',
                            y=selected_col,
                            title=f"{selected_col} par commune",
                            color=selected_col
                        )
                        fig.update_layout(xaxis_tickangle=-45)
                    
                    elif chart_type == "Camembert":
                        fig = px.pie(
                            plot_data,
                            values=selected_col,
                            names='Commune',
                            title=f"Répartition de {selected_col}"
                        )
                    
                    else:
                        fig = px.histogram(
                            plot_data,
                            x=selected_col,
                            title=f"Distribution de {selected_col}"
                        )
                    
                    st.plotly_chart(fig, use_container_width=True)
        
        # Bouton de retour
        st.markdown("---")
        if st.button("← Retour à l'accueil", key="back_viz"):
            st.session_state.page = "Accueil"
            st.rerun()

# --- PAGE DONNÉES ---
else:
    st.markdown('<div class="main-header">📋 Exploration des Données</div>', unsafe_allow_html=True)
    
    selected_sheet = st.selectbox(
        "Feuille:",
        list(data_dict.keys())
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        st.dataframe(df, use_container_width=True, height=400)
        
        # Export
        st.download_button(
            label="📥 Télécharger CSV",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name=f"{selected_sheet}.csv",
            mime="text/csv"
        )
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_data"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- FOOTER ---
st.divider()
st.caption(f"🌿 Agri-Analytics Chefchaouen • {len(data_dict)} feuilles • {datetime.now().strftime('%Y-%m-%d %H:%M')}")