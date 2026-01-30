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
    .answer-box {
        background-color: #e8f5e9;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #4caf50;
    }
    .warning-box {
        background-color: #fff3e0;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #ff9800;
    }
    .info-box {
        background-color: #e3f2fd;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #2196f3;
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

# --- SYSTÈME D'ANALYSE INTELLIGENT ---
class IntelligentAgriAnalyst:
    """Système d'analyse agricole intelligent"""
    
    def __init__(self, data_dict):
        self.data_dict = data_dict
        self.cache = {}
        self._build_crop_database()
    
    def _build_crop_database(self):
        """Construit une base de données des cultures"""
        self.crop_db = {}
        
        for sheet_name, df in self.data_dict.items():
            for col in df.columns:
                col_name = str(col).lower()
                
                # Détecter les cultures dans les noms de colonnes
                crops_found = self._detect_crops_in_column(col_name)
                
                for crop in crops_found:
                    if crop not in self.crop_db:
                        self.crop_db[crop] = {
                            'colonnes': [],
                            'feuilles': set(),
                            'type': self._get_crop_type(crop)
                        }
                    
                    self.crop_db[crop]['colonnes'].append({
                        'feuille': sheet_name,
                        'colonne': col,
                        'type': self._get_column_type(col_name)
                    })
                    self.crop_db[crop]['feuilles'].add(sheet_name)
    
    def _detect_crops_in_column(self, column_name):
        """Détecte les cultures dans un nom de colonne"""
        crops = []
        column_name = column_name.lower()
        
        # Liste complète des cultures avec variations
        crop_patterns = {
            'tomate': ['tomate', 'tomates'],
            'pomme de terre': ['pomme de terre', 'patate', 'pdt', 'p.terre'],
            'carotte': ['carotte', 'carottes'],
            'oignon': ['oignon', 'oignons'],
            'ail': ['ail'],
            'blé': ['blé', 'ble', 'bd'],
            'orge': ['orge', 'og'],
            'maïs': ['maïs', 'mais'],
            'avoine': ['avoine'],
            'fève': ['fève', 'feve'],
            'pois': ['pois'],
            'lentille': ['lentille'],
            'pois chiche': ['pois chiche', 'p.chiche'],
            'haricot': ['haricot'],
            'navet': ['navet'],
            'courgette': ['courgette'],
            'melon': ['melon'],
            'pastèque': ['pastèque', 'pasteque'],
            'chou': ['chou', 'choux'],
            'concombre': ['concombre'],
            'olivier': ['olivier', 'olive'],
            'figuier': ['figuier', 'figue'],
            'amandier': ['amandier', 'amande'],
            'vigne': ['vigne'],
            'cognassier': ['cognassier'],
            'caroubier': ['caroubier'],
            'grenadier': ['grenadier'],
            'prunier': ['prunier'],
            'pommier': ['pommier'],
            'poirier': ['poirier'],
            'cerisier': ['cerisier'],
            'pêcher': ['pêcher', 'pecher'],
            'abricot': ['abricot']
        }
        
        for crop, patterns in crop_patterns.items():
            for pattern in patterns:
                if pattern in column_name:
                    crops.append(crop)
                    break
        
        return list(set(crops))
    
    def _get_crop_type(self, crop):
        """Détermine le type de culture"""
        maraichage = ['tomate', 'pomme de terre', 'carotte', 'oignon', 'ail', 
                     'navet', 'courgette', 'melon', 'pastèque', 'chou', 'concombre']
        cereales = ['blé', 'orge', 'maïs', 'avoine']
        legumineuses = ['fève', 'pois', 'lentille', 'pois chiche', 'haricot']
        arboriculture = ['olivier', 'figuier', 'amandier', 'vigne', 'cognassier',
                        'caroubier', 'grenadier', 'prunier', 'pommier', 'poirier',
                        'cerisier', 'pêcher', 'abricot']
        
        if crop in maraichage:
            return 'maraichage'
        elif crop in cereales:
            return 'céréale'
        elif crop in legumineuses:
            return 'légumineuse'
        elif crop in arboriculture:
            return 'arboriculture'
        else:
            return 'autre'
    
    def _get_column_type(self, column_name):
        """Détermine le type de colonne"""
        if any(word in column_name for word in ['sup', 'surface', 'ha']):
            return 'surface'
        elif any(word in column_name for word in ['rdt', 'rendement', 'qx', 'production']):
            return 'rendement'
        elif any(word in column_name for word in ['nbre', 'nombre', 'quantité']):
            return 'quantité'
        else:
            return 'autre'
    
    def analyze_question(self, question):
        """Analyse une question et retourne une réponse structurée"""
        question_lower = question.lower()
        
        # Détecter le type de question
        question_type = self._detect_question_type(question_lower)
        
        # Détecter la culture demandée
        target_crop = self._detect_crop_in_question(question_lower)
        
        # Détecter la commune demandée
        target_commune = self._detect_commune_in_question(question_lower)
        
        # Analyser selon le type de question
        if question_type == 'max_surface':
            return self._answer_max_surface(target_crop, question)
        elif question_type == 'compare':
            return self._answer_comparison(target_crop, target_commune, question)
        elif question_type == 'list':
            return self._answer_list(target_crop, question)
        elif question_type == 'statistics':
            return self._answer_statistics(target_crop, question)
        elif question_type == 'recommendation':
            return self._answer_recommendation(target_crop, question)
        else:
            return self._answer_general(question)
    
    def _detect_question_type(self, question):
        """Détecte le type de question"""
        question = question.lower()
        
        if any(phrase in question for phrase in [
            'plus grand', 'plus grande', 'maximum', 'meilleur', 'meilleure',
            'quelle commune a', 'qui a le plus', 'le plus de'
        ]):
            return 'max_surface'
        
        elif any(phrase in question for phrase in [
            'comparer', 'différence', 'vs', 'versus', 'contre'
        ]):
            return 'compare'
        
        elif any(phrase in question for phrase in [
            'liste', 'quelles communes', 'où sont', 'qui cultive'
        ]):
            return 'list'
        
        elif any(phrase in question for phrase in [
            'statistique', 'moyenne', 'total', 'somme', 'combien'
        ]):
            return 'statistics'
        
        elif any(phrase in question for phrase in [
            'recommand', 'conseil', 'suggérer', 'proposer'
        ]):
            return 'recommendation'
        
        else:
            return 'general'
    
    def _detect_crop_in_question(self, question):
        """Détecte la culture dans la question"""
        for crop in self.crop_db.keys():
            crop_patterns = self._get_crop_patterns(crop)
            for pattern in crop_patterns:
                if pattern in question:
                    return crop
        return None
    
    def _detect_commune_in_question(self, question):
        """Détecte la commune dans la question"""
        communes = self._get_all_communes()
        for commune in communes:
            if commune.lower() in question:
                return commune
        return None
    
    def _get_crop_patterns(self, crop):
        """Retourne les patterns pour une culture"""
        patterns = {
            'tomate': ['tomate', 'tomates'],
            'pomme de terre': ['pomme de terre', 'patate', 'pdt'],
            'carotte': ['carotte', 'carottes'],
            'oignon': ['oignon', 'oignons'],
            'ail': ['ail'],
            'blé': ['blé', 'ble'],
            'orge': ['orge'],
            'maïs': ['maïs', 'mais'],
        }
        return patterns.get(crop, [crop.lower()])
    
    def _get_all_communes(self):
        """Récupère toutes les communes"""
        communes = set()
        for df in self.data_dict.values():
            if 'Commune' in df.columns:
                communes.update(df['Commune'].dropna().astype(str).str.strip().unique())
        return list(communes)
    
    def _answer_max_surface(self, crop, question):
        """Répond aux questions sur les maxima"""
        if not crop:
            return self._answer_general_max_surface(question)
        
        # Chercher les données pour cette culture
        crop_data = self._get_crop_surface_data(crop)
        
        if not crop_data:
            return self._build_no_data_response(crop, question)
        
        # Trouver la commune avec la plus grande surface
        max_row = crop_data.loc[crop_data['surface'].idxmax()]
        
        # Préparer la réponse
        response = f"""
        <div class='answer-box'>
        <h3>🏆 Résultat pour: "{question}"</h3>
        
        <h4>🥇 Commune avec la plus grande superficie de {crop}s:</h4>
        <div style='background-color: white; padding: 15px; border-radius: 8px; margin: 10px 0;'>
        <h2 style='color: #2E8B57; margin: 0;'>{max_row['commune']}</h2>
        <p style='font-size: 1.2em; margin: 5px 0;'><strong>{max_row['surface']} hectares</strong></p>
        </div>
        
        <h4>📊 Top 5 des communes:</h4>
        <table style='width: 100%; border-collapse: collapse;'>
        <tr style='background-color: #2E8B57; color: white;'>
            <th style='padding: 10px; text-align: left;'>Rang</th>
            <th style='padding: 10px; text-align: left;'>Commune</th>
            <th style='padding: 10px; text-align: left;'>Superficie (ha)</th>
        </tr>
        """
        
        top_5 = crop_data.nlargest(5, 'surface')
        for i, (_, row) in enumerate(top_5.iterrows(), 1):
            color = '#4caf50' if i == 1 else 'inherit'
            response += f"""
            <tr style='border-bottom: 1px solid #ddd;'>
                <td style='padding: 10px;'>{i}</td>
                <td style='padding: 10px; font-weight: bold; color: {color};'>{row['commune']}</td>
                <td style='padding: 10px;'>{row['surface']} ha</td>
            </tr>
            """
        
        response += f"""
        </table>
        
        <h4>📈 Statistiques générales:</h4>
        <ul>
            <li><strong>Superficie totale de {crop}s</strong>: {crop_data['surface'].sum():.1f} ha</li>
            <li><strong>Nombre de communes cultivant des {crop}s</strong>: {len(crop_data)}</li>
            <li><strong>Superficie moyenne</strong>: {crop_data['surface'].mean():.1f} ha</li>
            <li><strong>Superficie médiane</strong>: {crop_data['surface'].median():.1f} ha</li>
        </ul>
        
        <h4>🎯 Recommandations:</h4>
        <p>Pour développer la culture des {crop}s, concentrez-vous d'abord sur <strong>{max_row['commune']}</strong> 
        où l'expertise existe déjà, puis étendez progressivement aux autres communes du top 5.</p>
        </div>
        """
        
        # Créer un graphique
        fig = self._create_top_communes_chart(top_5, crop)
        
        return response, fig
    
    def _answer_general_max_surface(self, question):
        """Répond aux questions générales sur les maxima"""
        # Analyser toutes les cultures
        all_crops_data = []
        
        for crop in list(self.crop_db.keys())[:10]:  # Limiter aux 10 premières cultures
            crop_data = self._get_crop_surface_data(crop)
            if crop_data is not None and not crop_data.empty:
                max_surface = crop_data['surface'].max()
                if max_surface > 0:
                    max_commune = crop_data.loc[crop_data['surface'].idxmax(), 'commune']
                    all_crops_data.append({
                        'culture': crop,
                        'commune': max_commune,
                        'surface': max_surface
                    })
        
        if all_crops_data:
            df_all = pd.DataFrame(all_crops_data)
            df_all = df_all.sort_values('surface', ascending=False).head(5)
            
            response = f"""
            <div class='answer-box'>
            <h3>🌾 Réponse à: "{question}"</h3>
            
            <p>Voici les cultures avec les plus grandes superficies par commune:</p>
            
            <table style='width: 100%; border-collapse: collapse;'>
            <tr style='background-color: #2E8B57; color: white;'>
                <th style='padding: 10px; text-align: left;'>Culture</th>
                <th style='padding: 10px; text-align: left;'>Commune</th>
                <th style='padding: 10px; text-align: left;'>Superficie max (ha)</th>
            </tr>
            """
            
            for _, row in df_all.iterrows():
                response += f"""
                <tr style='border-bottom: 1px solid #ddd;'>
                    <td style='padding: 10px; font-weight: bold;'>🍅 {row['culture'].title()}</td>
                    <td style='padding: 10px;'>{row['commune']}</td>
                    <td style='padding: 10px;'>{row['surface']} ha</td>
                </tr>
                """
            
            response += """
            </table>
            
            <p><strong>Pour une réponse plus précise,</strong> posez une question spécifique comme:<br>
            • "Quelle commune a la plus grande superficie de tomates?"<br>
            • "Où sont les plus grandes surfaces d'oliviers?"<br>
            • "Quelle commune cultive le plus de blé?"</p>
            </div>
            """
            
            fig = px.bar(
                df_all,
                x='culture',
                y='surface',
                color='culture',
                title="Top des cultures par superficie maximale",
                labels={'culture': 'Culture', 'surface': 'Superficie (ha)'}
            )
            fig.update_layout(xaxis_tickangle=-45)
            
            return response, fig
        
        return self._answer_general(question)
    
    def _get_crop_surface_data(self, crop):
        """Récupère les données de surface pour une culture"""
        if crop not in self.crop_db:
            return None
        
        surface_data = []
        
        for col_info in self.crop_db[crop]['colonnes']:
            if col_info['type'] == 'surface':
                df = self.data_dict[col_info['feuille']]
                col_name = col_info['colonne']
                
                if col_name in df.columns:
                    for _, row in df.iterrows():
                        commune = row.get('Commune', 'Inconnue')
                        surface = row[col_name]
                        
                        if pd.notna(surface) and surface > 0 and commune != 'Inconnue':
                            surface_data.append({
                                'commune': commune,
                                'surface': surface,
                                'feuille': col_info['feuille'],
                                'colonne': col_name
                            })
        
        if surface_data:
            df_surface = pd.DataFrame(surface_data)
            # Agréger par commune (somme des surfaces)
            aggregated = df_surface.groupby('commune')['surface'].sum().reset_index()
            return aggregated
        
        return None
    
    def _create_top_communes_chart(self, data, crop):
        """Crée un graphique des top communes"""
        fig = px.bar(
            data,
            x='commune',
            y='surface',
            title=f"Top communes pour les {crop}s",
            color='surface',
            color_continuous_scale='greens',
            text='surface'
        )
        fig.update_traces(texttemplate='%{text} ha', textposition='outside')
        fig.update_layout(
            xaxis_title="Commune",
            yaxis_title="Superficie (hectares)",
            xaxis_tickangle=-45,
            showlegend=False
        )
        return fig
    
    def _build_no_data_response(self, crop, question):
        """Construit une réponse quand il n'y a pas de données"""
        response = f"""
        <div class='warning-box'>
        <h3>🔍 Analyse pour: "{question}"</h3>
        
        <p>Je n'ai pas trouvé de données spécifiques pour les <strong>{crop}s</strong> dans les feuilles chargées.</p>
        
        <h4>🔄 Suggestions:</h4>
        <ol>
            <li><strong>Vérifiez l'orthographe</strong> de la culture</li>
            <li><strong>Consultez les feuilles disponibles</strong> dans la page "📋 Données"</li>
            <li><strong>Essayez avec d'autres cultures</strong> comme:</li>
        </ol>
        
        <div style='display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0;'>
        """
        
        # Afficher les cultures disponibles
        available_crops = list(self.crop_db.keys())[:15]
        for available_crop in available_crops:
            response += f"""
            <div style='background-color: #4caf50; color: white; padding: 5px 10px; border-radius: 5px;'>
            {available_crop}
            </div>
            """
        
        response += """
        </div>
        
        <h4>📋 Feuilles qui pourraient contenir des données:</h4>
        <ul>
        """
        
        # Chercher les feuilles de maraîchage
        maraichage_sheets = [s for s in self.data_dict.keys() if 'maraichage' in s.lower() or 'maraîchage' in s.lower()]
        for sheet in maraichage_sheets[:5]:
            response += f"<li>{sheet}</li>"
        
        response += """
        </ul>
        
        <p><strong>Exemple de question précise:</strong><br>
        "Quelle commune a la plus grande superficie de tomates?"</p>
        </div>
        """
        
        return response, None
    
    def _answer_general(self, question):
        """Réponse générale"""
        response = f"""
        <div class='info-box'>
        <h3>🤖 Analyse Intelligente</h3>
        
        <p>J'ai analysé votre question: <strong>"{question}"</strong></p>
        
        <h4>🎯 Pour obtenir une réponse précise:</h4>
        
        <div style='background-color: white; padding: 15px; border-radius: 8px; margin: 10px 0;'>
        <h5 style='color: #2E8B57; margin-top: 0;'>📌 Posez des questions spécifiques:</h5>
        <ul>
            <li><strong>"Quelle commune a la plus grande superficie de [culture]?"</strong><br>
            Ex: "Quelle commune a la plus grande superficie de tomates?"</li>
            
            <li><strong>"Quels sont les meilleurs rendements en [culture]?"</strong><br>
            Ex: "Quels sont les meilleurs rendements en blé?"</li>
            
            <li><strong>"Quelles communes cultivent des [culture]?"</strong><br>
            Ex: "Quelles communes cultivent des oliviers?"</li>
            
            <li><strong>"Comparer [commune1] et [commune2] pour [culture]"</strong><br>
            Ex: "Comparer Bab Taza et Tanaqob pour les tomates"</li>
        </ul>
        </div>
        
        <h4>🌱 Cultures que je peux analyser:</h4>
        <div style='display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 15px 0;'>
        """
        
        # Afficher les cultures par catégorie
        crops_by_type = {}
        for crop, info in self.crop_db.items():
            crop_type = info['type']
            if crop_type not in crops_by_type:
                crops_by_type[crop_type] = []
            crops_by_type[crop_type].append(crop)
        
        for crop_type, crops in crops_by_type.items():
            response += f"""
            <div style='background-color: #f5f5f5; padding: 10px; border-radius: 5px;'>
                <strong>{crop_type.title()}:</strong><br>
                {', '.join(crops[:5])}
            </div>
            """
        
        response += """
        </div>
        
        <p><strong>💡 Astuce:</strong> Utilisez la page "🌱 Analyse Cultures" pour explorer une culture spécifique en détail.</p>
        </div>
        """
        
        return response, None

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
                
                # Chercher "Commune"
                header_idx = None
                for i, row in enumerate(raw[:10]):
                    row_lower = [str(cell).lower().strip() for cell in row]
                    if "commune" in row_lower:
                        header_idx = i
                        break
                
                if header_idx is None:
                    continue
                
                # En-têtes
                headers = raw[header_idx:header_idx+2]
                
                # Noms de colonnes
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
                
                # DataFrame
                df = pd.DataFrame(data_rows, columns=col_names)
                
                # Nettoyage
                for col in df.columns:
                    if 'commune' not in col.lower():
                        df[col] = df[col].apply(clean_val)
                
                # Colonne Commune
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
if 'page' not in st.session_state:
    st.session_state.page = "Accueil"
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'analyst' not in st.session_state:
    st.session_state.analyst = None

# Chargement
with st.spinner("🔄 Chargement des données agricoles..."):
    data_dict = load_data()
    
    if not data_dict:
        st.error("❌ Impossible de charger les données.")
        st.stop()
    
    if st.session_state.analyst is None:
        st.session_state.analyst = IntelligentAgriAnalyst(data_dict)
    
    st.success(f"✅ {len(data_dict)} feuilles chargées!")

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="main-header">🌿 Navigation</div>', unsafe_allow_html=True)
    
    # Navigation
    nav_options = {
        "🏠 Accueil": "Accueil",
        "🤖 Assistant IA": "Assistant",
        "🌱 Analyse Cultures": "Cultures",
        "📊 Visualisations": "Viz",
        "📋 Données": "Donnees"
    }
    
    for icon_text, page_value in nav_options.items():
        if st.button(icon_text, use_container_width=True, type="primary" if page_value == "Accueil" else "secondary"):
            st.session_state.page = page_value
            st.rerun()
    
    st.divider()
    
    # Stats
    if data_dict:
        total_rows = sum(len(df) for df in data_dict.values())
        total_communes = set()
        for df in data_dict.values():
            if 'Commune' in df.columns:
                total_communes.update(df['Commune'].unique())
        
        st.metric("Feuilles", len(data_dict))
        st.metric("Communes", len(total_communes))
        st.metric("Données", f"{total_rows:,}")
    
    st.divider()
    
    if st.button("🔄 Actualiser", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- PAGE ACCUEIL ---
if st.session_state.page == "Accueil":
    st.markdown('<div class="main-header">🌱 Agri-Analytics Chefchaouen</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 📊 Système d'Analyse Agricole Intelligent
        
        **🎯 Posez des questions en français naturel:**
        - "Quelle commune a la plus grande superficie de tomates?"
        - "Où sont les meilleurs rendements en blé?"
        - "Quelles communes cultivent des pommes de terre?"
        - "Comparer Bab Taza et Tanaqob pour l'irrigation"
        
        **🌿 Capacités d'analyse:**
        - 🔍 **Recherche intelligente** par culture
        - 📈 **Analyse comparative** des communes
        - 🏆 **Classements automatiques**
        - 📊 **Visualisations interactives**
        - 💡 **Recommandations personnalisées**
        
        **📋 Données analysables:**
        - 20+ cultures différentes
        - 27+ communes de Chefchaouen
        - Superficies, rendements, productions
        - Données d'irrigation et pédologiques
        """)
    
    with col2:
        st.markdown('<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px;">', unsafe_allow_html=True)
        st.markdown("### 🚀 Questions rapides")
        
        quick_qs = [
            ("🍅 Superficie tomates", "Quelle commune a la plus grande superficie de tomates?"),
            ("🥔 Meilleures pommes de terre", "Quelle commune a la plus grande superficie de pommes de terre?"),
            ("🥕 Top carottes", "Quelle commune a la plus grande superficie de carottes?"),
            ("🌾 Rendement blé", "Quelle commune a le meilleur rendement en blé?"),
            ("💧 Irrigation", "Quelles communes ont le plus d'irrigation?")
        ]
        
        for icon, question in quick_qs:
            if st.button(icon, use_container_width=True):
                st.session_state.page = "Assistant"
                st.session_state.quick_question = question
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Aperçu
    st.divider()
    st.markdown("### 📋 Cultures disponibles")
    
    if hasattr(st.session_state.analyst, 'crop_db'):
        crops = list(st.session_state.analyst.crop_db.keys())
        
        cols = st.columns(3)
        crops_per_col = len(crops) // 3 + 1
        
        for i in range(3):
            with cols[i]:
                start_idx = i * crops_per_col
                end_idx = min((i + 1) * crops_per_col, len(crops))
                for crop in crops[start_idx:end_idx]:
                    st.write(f"• {crop.title()}")

# --- PAGE ASSISTANT ---
elif st.session_state.page == "Assistant":
    st.markdown('<div class="main-header">🤖 Assistant Agricole Intelligent</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### 💬 Posez votre question en français naturel
    
    **Exemples de questions possibles:**
    - "Quelle commune a la plus grande superficie de [culture]?"
    - "Quels sont les meilleurs rendements en [culture]?"
    - "Quelles communes cultivent des [culture]?"
    - "Comparer [commune1] et [commune2] pour [culture]"
    - "Quelle est la superficie totale de [culture]?"
    """)
    
    # Saisie
    col1, col2 = st.columns([3, 1])
    
    with col1:
        user_question = st.text_input(
            "Votre question:",
            placeholder="Ex: Quelle commune a la plus grande superficie de carottes?",
            key="question_input"
        )
    
    with col2:
        analyze_btn = st.button("🔍 Analyser", use_container_width=True, type="primary")
    
    # Question rapide
    if 'quick_question' in st.session_state:
        user_question = st.session_state.quick_question
        del st.session_state.quick_question
        analyze_btn = True
    
    # Traitement
    if analyze_btn and user_question:
        # Historique
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_question,
            "time": datetime.now().strftime("%H:%M")
        })
        
        # Analyse
        with st.spinner("🔍 Analyse en cours..."):
            try:
                response_result = st.session_state.analyst.analyze_question(user_question)
                
                # Gérer le retour (peut être tuple ou simple valeur)
                if isinstance(response_result, tuple) and len(response_result) == 2:
                    response, chart = response_result
                else:
                    response = response_result
                    chart = None
                
            except Exception as e:
                response = f"""
                <div class='warning-box'>
                <h3>⚠️ Erreur d'analyse</h3>
                <p>Une erreur est survenue lors de l'analyse de votre question.</p>
                <p><strong>Erreur:</strong> {str(e)}</p>
                <p>Veuillez reformuler votre question ou essayer une autre requête.</p>
                </div>
                """
                chart = None
        
        # Ajouter à l'historique
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "chart": chart,
            "time": datetime.now().strftime("%H:%M")
        })
    
    # Historique
    st.markdown("---")
    st.markdown("### 📝 Historique des analyses")
    
    if not st.session_state.chat_history:
        st.info("👆 Posez votre première question ci-dessus pour commencer!")
    else:
        for message in reversed(st.session_state.chat_history[-3:]):
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
                    
                    if 'chart' in message and message['chart'] is not None:
                        st.plotly_chart(message['chart'], use_container_width=True)
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", use_container_width=True):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE CULTURES ---
elif st.session_state.page == "Cultures":
    st.markdown('<div class="main-header">🌱 Analyse par Culture</div>', unsafe_allow_html=True)
    
    if not hasattr(st.session_state.analyst, 'crop_db'):
        st.warning("Analyste non initialisé")
        st.stop()
    
    # Sélection
    crops = list(st.session_state.analyst.crop_db.keys())
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_crop = st.selectbox(
            "Sélectionnez une culture:",
            crops,
            format_func=lambda x: x.title()
        )
    
    with col2:
        analyze_btn = st.button("📊 Analyser", use_container_width=True, type="primary")
    
    if analyze_btn and selected_crop:
        with st.spinner(f"🔍 Analyse des {selected_crop}..."):
            crop_data = st.session_state.analyst._get_crop_surface_data(selected_crop)
        
        if crop_data is not None and not crop_data.empty:
            # Résultats
            st.markdown(f'<div class="answer-box"><h3>📈 Analyse des {selected_crop}s</h3>', unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Superficie totale", f"{crop_data['surface'].sum():.1f} ha")
            
            with col2:
                st.metric("Communes", len(crop_data))
            
            with col3:
                max_commune = crop_data.loc[crop_data['surface'].idxmax(), 'commune']
                max_surface = crop_data['surface'].max()
                st.metric("Meilleure commune", max_commune)
                st.caption(f"{max_surface} ha")
            
            # Graphique
            top_10 = crop_data.nlargest(10, 'surface')
            fig = px.bar(
                top_10,
                x='commune',
                y='surface',
                title=f"Top communes pour les {selected_crop}s",
                color='surface',
                color_continuous_scale='greens'
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            
            # Tableau
            st.dataframe(
                crop_data.sort_values('surface', ascending=False),
                use_container_width=True
            )
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning(f"Aucune donnée de superficie trouvée pour les {selected_crop}s")
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_cult"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE VISUALISATIONS ---
elif st.session_state.page == "Viz":
    st.markdown('<div class="main-header">📊 Visualisations</div>', unsafe_allow_html=True)
    
    selected_sheet = st.selectbox("Feuille:", list(data_dict.keys()))
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        # Colonnes numériques
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if numeric_cols and 'Commune' in df.columns:
            col1, col2 = st.columns([1, 3])
            
            with col1:
                selected_col = st.selectbox("Variable:", numeric_cols)
                chart_type = st.selectbox("Type:", ["Barres", "Camembert"])
                top_n = st.slider("Nombre:", 5, 30, 15)
            
            with col2:
                plot_data = df[['Commune', selected_col]].dropna()
                plot_data = plot_data.nlargest(top_n, selected_col)
                
                if chart_type == "Barres":
                    fig = px.bar(
                        plot_data,
                        x='Commune',
                        y=selected_col,
                        title=selected_col,
                        color=selected_col
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                else:
                    fig = px.pie(
                        plot_data,
                        values=selected_col,
                        names='Commune',
                        title=selected_col
                    )
                
                st.plotly_chart(fig, use_container_width=True)
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_viz"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE DONNÉES ---
else:
    st.markdown('<div class="main-header">📋 Exploration des Données</div>', unsafe_allow_html=True)
    
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille:",
        list(data_dict.keys()),
        key="data_select"
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        st.dataframe(df, use_container_width=True, height=400)
        
        # Export
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger CSV",
            data=csv,
            file_name=f"{selected_sheet}.csv",
            mime="text/csv"
        )
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_data"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- FOOTER ---
st.divider()
st.caption(f"🌿 Agri-Analytics Chefchaouen • {len(data_dict)} feuilles • {datetime.now().strftime('%H:%M')}")