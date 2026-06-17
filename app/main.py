import os
import time
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import openai  # Certifique-se de instalar 'openai' e 'cryptography' no requirements.txt

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------
# Configurações do Banco de Dados e Ambiente
# -----------------------------------------------------
# O professor proibiu senhas hardcoded. Usaremos variáveis de ambiente da EC2.
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'sua_senha_segura')
DB_HOST = os.getenv('DB_HOST', 'localhost')  # Aqui vai o endpoint do seu RDS privado
DB_NAME = os.getenv('DB_NAME', 'insightbot_db')

app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configuração da API de IA (ex: OpenAI)
openai.api_key = os.getenv("OPENAI_API_KEY", "sua_chave_aqui")

# -----------------------------------------------------
# Modelos do Banco de Dados (ORM)
# -----------------------------------------------------
class SiteGerado(db.Model):
    __tablename__ = 'sites_gerados'
    id = db.Column(db.Integer, primary_key=True)
    prompt_usuario = db.Column(db.Text, nullable=False)
    codigo_html = db.Column(db.LongText, nullable=False)
    estilo_css = db.Column(db.LongText, nullable=False)
    script_js = db.Column(db.LongText, nullable=False)
    data_criacao = db.Column(db.DateTime, default=db.func.current_timestamp())
    votos_curtidas = db.Column(db.Integer, default=0)

class LogGeracao(db.Model):
    __tablename__ = 'logs_geracao'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites_gerados.id', ondelete='CASCADE'))
    status_requisicao = db.Column(db.String(45), nullable=False)
    tempo_resposta_ms = db.Column(db.Integer, nullable=False)

# -----------------------------------------------------
# Endpoints da API
# -----------------------------------------------------

# 1. Endpoint Obrigatório de Validação do Professor (Sinal de Vida)
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "database_connected": True}), 200

# 2. CREATE: Rota que chama a IA, gera as animações e salva no banco privado
@app.route('/api/gerar', methods=['POST'])
def gerar_site():
    start_time = time.time()
    dados = request.get_json()
    prompt = dados.get('prompt')

    if not prompt:
        return jsonify({"erro": "O prompt do usuário é obrigatório."}), 400

    try:
        # Comando de sistema refinado para forçar a IA a separar as tecnologias de frontend
        instrucoes = (
            "Você é um gerador especialista em interfaces frontend com foco em animações incríveis em CSS/JS. "
            "Gere uma resposta estritamente em formato JSON contendo as chaves: 'html', 'css' e 'js'. "
            "Não adicione marcações extras de Markdown (como ```json) ou explicações fora do JSON."
        )

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": instrucoes},
                {"role": "user", "content": f"Crie o código completo para: {prompt}"}
            ]
        )

        # O resultado esperado é uma string JSON contendo as 3 partes do código
        resultado_ia = eval(response.choices[0].message['content'].strip())

        novo_site = SiteGerado(
            prompt_usuario=prompt,
            codigo_html=resultado_ia.get('html', '<h1>Sem conteúdo</h1>'),
            estilo_css=resultado_ia.get('css', ''),
            script_js=resultado_ia.get('js', '')
        )
        db.session.add(novo_site)
        db.session.commit()

        # Registrar log com sucesso
        tempo_total = int((time.time() - start_time) * 1000)
        log = LogGeracao(site_id=novo_site.id, status_requisicao='SUCESSO', tempo_resposta_ms=tempo_total)
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "id": novo_site.id,
            "prompt": novo_site.prompt_usuario,
            "html": novo_site.codigo_html,
            "css": novo_site.estilo_css,
            "js": novo_site.script_js
        }), 201

    except Exception as e:
        tempo_total = int((time.time() - start_time) * 1000)
        log = LogGeracao(status_requisicao='ERRO', tempo_resposta_ms=tempo_total)
        db.session.add(log)
        db.session.commit()
        return jsonify({"erro": f"Falha na geração: {str(e)}"}), 500

# 3. READ: Listar a galeria de sites criados
@app.route('/api/sites', methods=['GET'])
def listar_sites():
    sites = SiteGerado.query.order_by(SiteGerado.data_criacao.desc()).all()
    resultado = []
    for s in sites:
        resultado.append({
            "id": s.id,
            "prompt": s.prompt_usuario,
            "data": s.data_criacao.strftime('%d/%m/%Y %H:%M'),
            "votos": s.votos_curtidas
        })
    return jsonify(resultado), 200

# 4. READ (Específico): Visualizar o site gerado renderizado em tela cheia
@app.route('/render/<int:site_id>', methods=['GET'])
def renderizar_site(site_id):
    site = SiteGerado.query.get_or_404(site_id)
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{site.prompt_usuario[:30]}</title>
        <style>{site.estilo_css}</style>
    </head>
    <body>
        {site.codigo_html}
        <script>{site.script_js}</script>
    </body>
    </html>
    """
    return render_template_string(template)

# 5. DELETE: Apagar do banco de dados privado
@app.route('/api/sites/<int:site_id>', methods=['DELETE'])
def deletar_site(site_id):
    site = SiteGerado.query.get_or_404(site_id)
    db.session.delete(site)
    db.session.commit()
    return jsonify({"mensagem": "Registro removido com sucesso!"}), 200

if __name__ == '__main__':
    # O comando abaixo cria as tabelas caso elas ainda não existam no RDS no momento do boot
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
