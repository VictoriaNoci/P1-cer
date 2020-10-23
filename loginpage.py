from flask import Flask, render_template, redirect, request, url_for, session, flash
from elasticsearch import Elasticsearch
import hashlib
import os
import requests
import re
import time, threading

app = Flask(__name__)
app.secret_key = "ayush"

es=Elasticsearch([{'host':'localhost','port':9200}]) #Conexion con BBDD local

salt = os.urandom(16)

def peticion_n_aleatorio(segundos):
    while(True):
        n_aleatorio = requests.get('https://numero.wiki/generadores/servicio-json/?desde=100&hasta=1&numero=1&repeticion=1&json=0')
        numero = (re.search('\[(.*?)\]', n_aleatorio.text))[0]    # Obtenemos valor entre corchetes
        numero = numero[ 1:len(numero) - 1]    # Quitamos corchetes
        print('\nNUEVO NUMERO ALEATORIO: '+ str(numero))

        # INSERCCIÓN EN BBDD Internet
        inserccion = requests.get('https://api.thingspeak.com/update?api_key=NG06GVW5ISHZGWSR&field1=' + str(numero))
        print(str(numero) + " añadido a BBDD Internet")

        # INSERCCIÓN BBDD local
        numero_body={"value":numero}
        n_numeros= es.search(index='aleatorios')  # Obtener nº usuarios para añadir 1 más
        n_numeros = n_numeros['hits']['total'] + 1  # ID + 1
        respuesta = es.index(index='aleatorios',doc_type='data',id=n_numeros,body=numero_body)
        if (respuesta['result'] == 'created'):
            print(str(numero) + " añadido a BBDD local")

        time.sleep(segundos)

@app.route('/')
def home():
    if 'email' in session:
        return render_template('index.html',msj=session['user'] + " está conectado")
    return render_template("index.html")

@app.route('/register')
def register():
    if 'email' in session:
        session.clear()  # Cerramos sesión antes de iniciar una nueva
    return render_template("newuser.html")
@app.route('/success',methods = ["POST"])
def success():
    if request.method == "POST":
        session['email']=request.form['email']
        session['user']=request.form['user']
        session['pass']=request.form['pass']

    hash = hashlib.pbkdf2_hmac('sha256', b'password', salt, 100000)

    user_data={"username":session['user'],"email":session['email'],"password":session['pass']}
    user_data_field={"field1":session['user'],"field2":session['email'],"field3":session['pass']}

    n_usuarios= es.search(index='usuarios')  # Obtener nº usuarios para añadir 1 más
    n_usuarios = n_usuarios['hits']['total'] + 1  # ID + 1

    # Insercción en BBDD local
    nombre_usuario= es.search(index='usuarios',body={'query':{'match':{'username':session['user']}}})      # POR API
    if (nombre_usuario['hits']['total'] == 0):      # No hay nadie con ese nombre de usuario
        #email_usuario= es.search(index='usuarios',body={'query':{'match':{'email':session['email']}}})
        email_usuario= requests.get('http://localhost:9200/usuarios/data/_search?q=email:"'+ session['email'] + '"&pretty')     # POR URL
        if(email_usuario.json()['hits']['total'] == 0):    # No hay nadie con ese email
            respuesta = es.index(index='usuarios',doc_type='data',id=n_usuarios,body=user_data)
            if (respuesta['result'] == 'created'):
                print(str(session['user']) + ": USUARIO CREADO con id = " + str(n_usuarios) + '\n')
                print(str(session['user']) + ": SESIÓN INICIADA\n")
                return render_template('index.html',msj=session['user'] + " está conectado")
        else:
            return render_template('newuser.html',msj="Email: " + session['email'] + " ya existe. Inicia sesión.")
    else:
        return render_template('newuser.html',msj="Nombre de usuario: " + session['user'] + " ya existe. Inicia sesión o elige otro")

@app.route('/login')
def login():
    if 'email' in session:
        return render_template('index.html',msj=session['user'] + " está conectado")
    else:
        return render_template("login.html")
@app.route('/success_login',methods = ["POST"])
def success_login():
    session['email']=request.form['email']
    session['pass']=request.form['pass']

    # Comprobar que existe en la BBDD
    #email_usuario= es.search(index='usuarios',body={'query':{'match':{'email':session['email']}}})
    email_usuario= requests.get('http://localhost:9200/usuarios/data/_search?q=email:"'+ session['email'] + '"&pretty')     # POR URL
    if (email_usuario.json()['hits']['total'] == 1):      # Hemos encontrado su email
        session['user']= email_usuario.json()['hits']['hits'][0]['_source']['username']   # Añadimos a variables de sesion el nombre de usuario
        if (email_usuario.json()['hits']['hits'][0]['_source']['password'] == session['pass']):   # Comprobamos que la contraseña es correcta
            print(str(session['user']) + ": SESIÓN INICIADA\n")
            return render_template('index.html',msj=session['user'] + " está conectado")
        else:
            return render_template('login.html',msj="La contraseña introducida no es correcta.")
    else:
        return render_template('login.html',msj="Email: " + session['email'] + " no existe en nuestra BBDD. ¡Regístrate primero!")

@app.route('/logout')
def logout():
    if 'email' in session:      # Hay una sesión iniciada
        print(str(session['user']) + ": SESIÓN CERRADA\n")
        session.clear()
        return render_template('index.html',msj="Se ha cerrado la sesión")
    else:
        return render_template('index.html',msj="Para cerrar sesión, primero inicia")

@app.route('/media_1',methods = ["POST"])
def media_1():   # Solo disponible para usuarios registrados y +1 peticiones dentro ficha BBDD
    if 'user' in session:      # Hay una sesión iniciada
        n_aleatorios= es.search(index='aleatorios')  # Obtener nº de números aleatorios en la bbdd
        n_aleatorios = n_aleatorios['hits']['total']
        media = 0
        for i in range(n_aleatorios):
            numero= requests.get('http://localhost:9200/aleatorios/data/'+ str(i+1) +'?pretty')
            media = media + int(numero.json()['_source']['value'])
        media = media/n_aleatorios
        return render_template('index.html',msj=session['user'] + " está conectado",media1="Media BBDD local: " + str(media))
    else:
        return render_template('index.html',msj="Media solo disponible para usuarios registrados")

@app.route('/media_2',methods = ["POST"])    # BBDD internet
def media_2():
    if 'user' in session:      # Hay una sesión iniciada
        lista_aleatorios = requests.get('https://api.thingspeak.com/channels/1194117/feeds.json?api_key=ER2RW1ORI6791BT2')
        #print('Lista ' + str(lista_aleatorios.json()))
        n_datos = lista_aleatorios.json()['channel']['last_entry_id']
        media = 0
        for i in range(n_datos):
            media = media + int(lista_aleatorios.json()['feeds'][i]['field1'])
        media = media/n_datos
        print('Media BBDD internet: ' + str(media))
        return render_template('index.html',msj=session['user'] + " está conectado",media2="Media BBDD internet: " + str(media))
    else:
        return render_template('index.html',msj="Media solo disponible para usuarios registrados")

@app.route('/umbral_historico',methods = ["POST"])
def umbral_historico():    # 5 últimos valores en los que se superó umbral
    if 'user' in session:      # Hay una sesión iniciada
        umbral=request.form['umbral']
        lista_aleatorios = requests.get('https://api.thingspeak.com/channels/1194117/feeds.json?api_key=ER2RW1ORI6791BT2')
        n_datos = int(lista_aleatorios.json()['channel']['last_entry_id'])
        n_datos_encontrados = 0
        lista_valores = []
        for i in range(n_datos):
            if n_datos_encontrados < 5:
                numero = int(lista_aleatorios.json()['feeds'][n_datos-i-1]['field1'])
                if numero > int(umbral):
                    lista_valores.append(numero)
                    n_datos_encontrados = n_datos_encontrados + 1
        return render_template('index.html',umbral="Últimos 5 valores que han superado el umbral: " + str(lista_valores))
    else:
        return render_template('index.html',msj="Calculo umbral solo disponible para usuarios registrados")

if __name__ == "__main__":
    hilo_n_aleatorio = threading.Thread(target=peticion_n_aleatorio, args=(60,))  # Peticion del numero cada 120s
    hilo_n_aleatorio.setDaemon(True) # Ejecucion sin bloquear hilo principal
    hilo_n_aleatorio.start()
    app.run(host='0.0.0.0', port=5000, debug=True, user_reloader=False)
