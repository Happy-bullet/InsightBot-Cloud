import os
import time
import json
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from google import genai  # Novo SDK oficial do Google

app = Flask(__name__)
CORS(app)

# Configurações do Banco de Dados
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'sua_senha')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'insightbot_db')

app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Inicializando o cliente moderno do Gemini
# Ele coleta automaticamente a variável de ambiente GEMINI_API_KEY
client = genai.Client()

class SiteGerado(db.Model):
    __tablename__ = 'sites_gerados'
    id = db.Column(db.Integer, primary_key=True)
    prompt_usuario = db.Column(db.Text, nullable=False)
    codigo_html = db.Column(db.Text, nullable=False)
    estilo_css = db.Column(db.Text, nullable=False)
    script_js = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, default=db.func.current_timestamp())

@app.route('/')
def home():
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            conteudo = f.read()
        return render_template_string(conteudo)
    except Exception as e:
        return f"Erro ao carregar o arquivo templates/index.html: {str(e)}", 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "database_connected": True}), 200

@app.route('/api/gerar', methods=['POST'])
def gerar_site():
    dados = request.get_json()
    prompt = dados.get('prompt')

    if not prompt:
        return jsonify({"erro": "O prompt é obrigatório."}), 400

    try:
        instrucoes = (
            "Você é um gerador especialista em interfaces frontend com foco em animações em CSS/JS. "
            "Gere uma resposta estritamente em formato JSON estruturado com três chaves de strings: "
            "'html', 'css' e 'js'. Não adicione blocos de código markdown como ```json."
        )

        # Chamada corrigida usando estritamente o padrão do novo SDK (client.models.generate_content)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{instrucoes} Crie o código para: {prompt}"
        )
        
        texto_puro = response.text.strip()
        
        # Limpeza preventiva contra blocos de Markdown residuais
        if texto_puro.startswith("```json"):
            texto_puro = texto_puro.split("```json")[1]
        if texto_puro.endswith("```"):
            texto_puro = texto_puro.rsplit("```", 1)[0]
        texto_puro = texto_puro.strip()

        resultado_ia = json.loads(texto_puro)

        novo_site = SiteGerado(
            prompt_usuario=prompt,
            codigo_html=resultado_ia.get('html', '<h1>Sem conteúdo</h1>'),
            estilo_css=resultado_ia.get('css', ''),
            script_js=resultado_ia.get('js', '')
        )
        db.session.add(novo_site)
        db.session.commit()

        return jsonify({
            "id": novo_site.id,
            "prompt": novo_site.prompt_usuario,
            "html": novo_site.codigo_html,
            "css": novo_site.estilo_css,
            "js": novo_site.script_js
        }), 201

    except Exception as e:
        print("--- ERRO NA GERACAO ---")
        import traceback
        traceback.print_exc()
        print("-----------------------")
        return jsonify({"erro": f"Falha na geração: {str(e)}"}), 500

@app.route('/api/sites', methods=['GET'])
def listar_sites():
    try:
        sites = SiteGerado.query.order_by(SiteGerado.data_criacao.desc()).all()
        return jsonify([{"id": s.id, "prompt": s.prompt_usuario, "data": s.data_criacao.strftime('%d/%m/%Y %H:%M')} for s in sites]), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/render/<int:site_id>', methods=['GET'])
def renderizar_site(site_id):
    site = SiteGerado.query.get_or_404(site_id)
    return render_template_string(f"<!DOCTYPE html><html><head><style>{site.estilo_css}</style></head><body>{site.codigo_html}<script>{site.script_js}</script></body></html>")

@app.route('/api/sites/<int:site_id>', methods=['DELETE'])
def deletar_site(site_id):
    site = SiteGerado.query.get_or_404(site_id)
    db.session.delete(site)
    db.session.commit()
    return jsonify({"mensagem": "Removido!"}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
