"""
myCloudNote Backend mcn
Application Flask pour la gestion des utilisateurs et la synchronisation avec CouchDB
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import bcrypt
import couchdb
from datetime import datetime, timedelta
from functools import wraps
import os
import uuid
import requests
from user_agents import parse

app = Flask(__name__)
CORS(app)

# Configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'votre-cle-secrete-a-changer')
COUCHDB_URL = os.environ.get('COUCHDB_URL', 'https://admin:admin@couchdb.mcn.ngling.tech/')
TOKEN_EXPIRY_DAYS = 30

# Connexion à CouchDB
couch = couchdb.Server(COUCHDB_URL)

# Base de données utilisateurs
try:
    users_db = couch['users']
except:
    users_db = couch.create('users')

# onction helper pour envoyer des SMS WhatsApp
def send_whatsapp_message(phone_number, message):
    """Envoyer un message WhatsApp"""
    try:
        # Remplacer par votre mcn WhatsApp (ex: Twilio, WhatsApp Business mcn, etc.)
        payload = {
        "args": {
            "to":  phone_number.replace('+', '') + "@c.us",
            "content": message
        }
        }
        headers = {
            'Content-Type': 'application/json'
        }
        print(payload)
        
        response = requests.post("https://whatsapp.ngling.tech/sendText", json=payload, headers=headers)
        print('******************************************************************\n', message)
        return response.status_code == 200
    except Exception as e:
        print(f"Erreur envoi WhatsApp: {e}")
        return False

# Fonction pour générer un code de confirmation
def generate_confirmation_code():
    """Générer un code de confirmation à 6 chiffres"""
    import random
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

# Fonction pour parser les informations de l'appareil
def get_device_info(request):
    """Extraire les informations de l'appareil depuis le User-Agent"""
    user_agent = request.headers.get('User-Agent', '')
    ua = parse(user_agent)
    
    return {
        'device_id': str(uuid.uuid4()),
        'device_name': f"{ua.device.family} {ua.device.model}".strip() or "Appareil inconnu",
        'browser': f"{ua.browser.family} {ua.browser.version_string}",
        'os': f"{ua.os.family} {ua.os.version_string}",
        'is_mobile': ua.is_mobile,
        'is_tablet': ua.is_tablet,
        'is_pc': ua.is_pc,
        'user_agent': user_agent,
        'connected_at': datetime.utcnow().isoformat()
    }


# Middleware de vérification du token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token manquant'}), 401
        
        try:
            # Retirer le préfixe "Bearer " si présent
            if token.startswith('Bearer '):
                token = token[7:]
            
            # Décoder le token
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            current_user = data['user_id']
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expiré'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token invalide'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

@app.route('/mcn/register', methods=['POST'])
def register():
    """Inscription d'un nouvel utilisateur avec confirmation WhatsApp"""
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password') or not data.get('whatsapp'):
        return jsonify({'error': 'Email, mot de passe et numéro WhatsApp requis'}), 400
    
    email = data['email'].lower().strip()
    password = data['password']
    whatsapp = data['whatsapp'].strip()
    
    # Vérifier si l'utilisateur existe déjà
    for doc_id in users_db:
        doc = users_db[doc_id]
        if doc.get('email') == email:
            return jsonify({'error': 'Cet email est déjà utilisé'}), 409
    
    # Hasher le mot de passe
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    # Générer le code de confirmation
    confirmation_code = generate_confirmation_code()
    # confirmation_code = "505050"
    
    # Créer l'utilisateur
    user_doc = {
        'email': email,
        'password': password_hash.decode('utf-8'),
        'whatsapp': whatsapp,
        'confirmed': False,
        'confirmation_code': confirmation_code,
        'created_at': datetime.utcnow().isoformat(),
        'preferences': {
            'view_mode': 'grid'
        },
        'devices': []
    }
    
    doc_id, doc_rev = users_db.save(user_doc)
    
    # Créer une base de données personnelle
    db_name = f'notes_{doc_id}'
    try:
        couch.create(db_name)
    except:
        pass
    
    # Envoyer le code de confirmation par WhatsApp
    message = f"Bienvenue sur myCloudNote ! Votre code de confirmation est : {confirmation_code}"
    send_whatsapp_message(whatsapp, message)
    
    return jsonify({
        'message': 'Compte créé. Vérifiez votre WhatsApp pour le code de confirmation.',
        'user_id': doc_id,
        'requires_confirmation': True
    }), 201

# AJOUTER cette nouvelle route
@app.route('/mcn/confirm', methods=['POST'])
def confirm_account():
    """Confirmer le compte avec le code WhatsApp"""
    data = request.get_json()
    
    if not data or not data.get('user_id') or not data.get('code'):
        return jsonify({'error': 'ID utilisateur et code requis'}), 400
    
    user_id = data['user_id']
    code = data['code']
    
    try:
        user_doc = users_db[user_id]
    except:
        return jsonify({'error': 'Utilisateur non trouvé'}), 404
    
    if user_doc.get('confirmation_code') != code:
        return jsonify({'error': 'Code de confirmation incorrect'}), 401
    
    # Marquer comme confirmé
    user_doc['confirmed'] = True
    user_doc['confirmation_code'] = None
    
    # Ajouter l'appareil
    device_info = get_device_info(request)
    user_doc['devices'] = [device_info]
    
    users_db[user_id] = user_doc
    
    # Générer le token
    token = jwt.encode({
        'user_id': user_id,
        'email': user_doc['email'],
        'device_id': device_info['device_id'],
        'exp': datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS)
    }, SECRET_KEY, algorithm='HS256')
    
    return jsonify({
        'message': 'Compte confirmé avec succès',
        'token': token,
        'user_id': user_id,
        'db_name': f'notes_{user_id}',
        'device_id': device_info['device_id']
    }), 200

# REMPLACER la route /mcn/login
@app.route('/mcn/login', methods=['POST'])
def login():
    """Connexion avec email ou WhatsApp"""
    data = request.get_json()
    
    if not data or not data.get('identifier') or not data.get('password'):
        return jsonify({'error': 'Identifiant et mot de passe requis'}), 400
    
    identifier = data['identifier'].lower().strip()
    password = data['password']
    
    # Rechercher l'utilisateur par email ou WhatsApp
    user_doc = None
    user_id = None
    
    for doc_id in users_db:
        doc = users_db[doc_id]
        if doc.get('email') == identifier or doc.get('whatsapp') == identifier:
            user_doc = doc
            user_id = doc_id
            break
    
    if not user_doc:
        return jsonify({'error': 'Identifiant ou mot de passe incorrect'}), 401
    
    # Vérifier si le compte est confirmé
    if not user_doc.get('confirmed', False):
        return jsonify({'error': 'Compte non confirmé. Veuillez confirmer votre compte.', 'requires_confirmation': True, 'user_id': user_id}), 403
    
    # Vérifier le mot de passe
    if not bcrypt.checkpw(password.encode('utf-8'), user_doc['password'].encode('utf-8')):
        return jsonify({'error': 'Identifiant ou mot de passe incorrect'}), 401
    
    # Récupérer les informations de l'appareil
    device_info = get_device_info(request)
    
    # Vérifier si c'est un nouvel appareil
    existing_devices = user_doc.get('devices', [])
    device_exists = any(d.get('user_agent') == device_info['user_agent'] for d in existing_devices)
    
    if not device_exists:
        # Nouvel appareil détecté
        existing_devices.append(device_info)
        user_doc['devices'] = existing_devices
        users_db[user_id] = user_doc
        
        # Envoyer une alerte WhatsApp
        message = f"""🔔 Nouvelle connexion détectée sur myCloudNote
        
Appareil: {device_info['device_name']}
Navigateur: {device_info['browser']}
Système: {device_info['os']}
Date: {datetime.utcnow().strftime('%d/%m/%Y à %H:%M')}

Si ce n'est pas vous, sécurisez votre compte immédiatement."""
        
        send_whatsapp_message(user_doc['whatsapp'], message)
    
    # Générer le token
    token = jwt.encode({
        'user_id': user_id,
        'email': user_doc['email'],
        'device_id': device_info['device_id'],
        'exp': datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS)
    }, SECRET_KEY, algorithm='HS256')
    
    return jsonify({
        'message': 'Connexion réussie',
        'token': token,
        'user_id': user_id,
        'db_name': f'notes_{user_id}',
        'preferences': user_doc.get('preferences', {'view_mode': 'grid'}),
        'device_id': device_info['device_id'],
        'is_new_device': not device_exists
    }), 200

# AJOUTER ces nouvelles routes
@app.route('/mcn/devices', methods=['GET'])
@token_required
def get_devices(current_user):
    """Récupérer la liste des appareils connectés"""
    user_doc = users_db[current_user]
    devices = user_doc.get('devices', [])
    
    return jsonify({'devices': devices}), 200

@app.route('/mcn/devices/<device_id>', methods=['DELETE'])
@token_required
def remove_device(current_user, device_id):
    """Supprimer un appareil"""
    user_doc = users_db[current_user]
    devices = user_doc.get('devices', [])
    
    # Filtrer l'appareil à supprimer
    user_doc['devices'] = [d for d in devices if d.get('device_id') != device_id]
    users_db[current_user] = user_doc
    
    return jsonify({'message': 'Appareil supprimé'}), 200

@app.route('/mcn/account', methods=['GET', 'PUT'])
@token_required
def account_settings(current_user):
    """Gérer les paramètres du compte"""
    user_doc = users_db[current_user]
    
    if request.method == 'GET':
        return jsonify({
            'email': user_doc['email'],
            'whatsapp': user_doc['whatsapp'],
            'created_at': user_doc['created_at'],
            'preferences': user_doc.get('preferences', {}),
            'devices_count': len(user_doc.get('devices', []))
        }), 200
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        # Mise à jour des informations
        if 'whatsapp' in data:
            user_doc['whatsapp'] = data['whatsapp']
        
        if 'password' in data and data['password']:
            password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
            user_doc['password'] = password_hash.decode('utf-8')
        
        users_db[current_user] = user_doc
        
        return jsonify({'message': 'Compte mis à jour'}), 200

@app.route('/mcn/verify', methods=['GET'])
@token_required
def verify_token(current_user):
    """Vérifier la validité du token"""
    user_doc = users_db[current_user]
    
    return jsonify({
        'valid': True,
        'user_id': current_user,
        'email': user_doc['email'],
        'db_name': f'notes_{current_user}',
        'preferences': user_doc.get('preferences', {'view_mode': 'grid'})
    }), 200

@app.route('/mcn/preferences', methods=['GET', 'PUT'])
@token_required
def preferences(current_user):
    """Récupérer ou mettre à jour les préférences utilisateur"""
    user_doc = users_db[current_user]
    
    if request.method == 'GET':
        return jsonify(user_doc.get('preferences', {'view_mode': 'grid'})), 200
    
    elif request.method == 'PUT':
        data = request.get_json()
        user_doc['preferences'] = data
        users_db[current_user] = user_doc
        
        return jsonify({
            'message': 'Préférences mises à jour',
            'preferences': user_doc['preferences']
        }), 200

@app.route('/mcn/health', methods=['GET'])
def health():
    """Endpoint de santé de l'mcn"""
    return jsonify({'status': 'ok', 'service': 'myCloudNote mcn'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)