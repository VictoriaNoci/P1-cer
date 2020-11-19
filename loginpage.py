from flask import Flask, render_template, redirect, request, url_for, session, flash
from elasticsearch import Elasticsearch
import hashlib
import uuid
import os
import requests
import re
import time, threading
import base64

app = Flask(__name__)
numero_global = 101
app.secret_key = "ayush"

es=Elasticsearch([{'host':'localhost','port':9200}]) #Conexion con BBDD local

salt = uuid.uuid4().hex

def peticion_n_aleatorio(segundos, numero_global):
    while(True):
        n_aleatorio = requests.get('https://numero.wiki/generadores/servicio-json/?desde=100&hasta=1&numero=1&repeticion=1&json=0')
        numero = (re.search('\[(.*?)\]', n_aleatorio.text))[0]    # Obtenemos valor entre corchetes
        numero = numero[ 1:len(numero) - 1]    # Quitamos corchetes
        print('\nNUEVO NUMERO ALEATORIO: '+ str(numero))

        if numero_global == 101:
            global n_global
            n_global = numero
            numero_global = numero

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
        return render_template('index.html',msj=session['user'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']),n_aleatorio='Primer número: ' + str(n_global))
    return render_template("index.html",n_aleatorio='Primer número: ' + str(n_global))

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
        session['peticiones']=0

    key = hashlib.sha256(salt.encode() + session['pass'].encode()).hexdigest() + ':' + salt
    user_data={"username":session['user'],"email":session['email'],"password":key,"peticiones":0}

    n_usuarios= es.search(index='usuarios')  # Obtener nº usuarios para añadir 1 más
    n_usuarios = n_usuarios['hits']['total'] + 1  # ID + 1

    # Inserción en BBDD local
    nombre_usuario= es.search(index='usuarios',body={'query':{'match':{'username':session['user']}}})      # POR API
    if (nombre_usuario['hits']['total'] == 0):      # No hay nadie con ese nombre de usuario
        email_usuario= requests.get('http://localhost:9200/usuarios/data/_search?q=email:"'+ session['email'] + '"&pretty')     # POR URL
        if(email_usuario.json()['hits']['total'] == 0):    # No hay nadie con ese email
            respuesta = es.index(index='usuarios',doc_type='data',id=n_usuarios,body=user_data)
            if (respuesta['result'] == 'created'):
                print(str(session['user']) + ": USUARIO CREADO con id = " + str(n_usuarios) + '\n')
                print(str(session['user']) + ": SESIÓN INICIADA\n")
                return render_template('index.html',msj=session['user'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']))
        else:
            return render_template('newuser.html',msj="Email: " + session['email'] + " ya existe. Inicia sesión.")
    else:
        return render_template('newuser.html',msj="Nombre de usuario: " + session['user'] + " ya existe. Inicia sesión o elige otro")

@app.route('/login')
def login():
    if 'email' in session:
        return render_template('index.html',msj=session['email'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']))
    else:
        return render_template("login.html")
@app.route('/success_login',methods = ["POST"])
def success_login():
    email=request.form['email']
    password_introducida=request.form['pass']

    # Comprobar que existe en la BBDD
    email_usuario= requests.get('http://localhost:9200/usuarios/data/_search?q=email:"'+ email + '"&pretty')     # POR URL
    if (email_usuario.json()['hits']['total'] == 1):      # Hemos encontrado su email (Usuario existe)
        session['user']= email_usuario.json()['hits']['hits'][0]['_source']['username']   # Añadimos a variables de sesion el nombre de usuario
        session['email']= email
        session['peticiones']= email_usuario.json()['hits']['hits'][0]['_source']['peticiones']   # Añadimos a variables de sesión el número de peticiones
        session['pass'] = password_introducida

        pass_hasheada = email_usuario.json()['hits']['hits'][0]['_source']['password'] # Comprobamos que la contraseña es correcta
        password, salt = pass_hasheada.split(':')
        pass_introducida = hashlib.sha256(salt.encode() + session['pass'].encode()).hexdigest()
        if (password == pass_introducida):
            print(str(session['user']) + ": SESIÓN INICIADA\n")
            return render_template('index.html',msj=session['user'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']))
        else:
            return render_template('login.html',msj="La contraseña introducida no es correcta.")
    else:
        return render_template('login.html',msj="Email: " + email + " no existe en nuestra BBDD. ¡Regístrate primero!")

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
    if 'email' in session:      # Hay una sesión iniciada
        n_aleatorios= es.search(index='aleatorios')  # Obtener nº de números aleatorios en la bbdd
        n_aleatorios = n_aleatorios['hits']['total']
        print('N elementos LOCAL: ' + str(n_aleatorios))
        media = 0
        for i in range(n_aleatorios):
            numero= requests.get('http://localhost:9200/aleatorios/data/'+ str(i+1) +'?pretty')
            media = media + int(numero.json()['_source']['value'])
        media = media/n_aleatorios

        # +1 en n_peticiones del usuario
        usuario= es.search(index='usuarios',body={'query':{'match':{'username':session['user']}}})
        datos_usuario = usuario['hits']['hits'][0]['_source']
        datos_usuario['peticiones']= datos_usuario['peticiones'] + 1
        session['peticiones'] = datos_usuario['peticiones']
        respuesta = es.index(index='usuarios',doc_type='data',id=usuario['hits']['hits'][0]['_id'],body=datos_usuario)
        if (respuesta['result'] == 'updated'):
            return render_template('index.html',msj=session['user'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']),media="Media BBDD local: " + str(media))
    else:
        return render_template('index.html',msj="Media solo disponible para usuarios registrados")

@app.route('/media_2',methods = ["POST"])    # BBDD internet
def media_2():
    if 'email' in session:      # Hay una sesión iniciada
        lista_aleatorios = requests.get('https://api.thingspeak.com/channels/1194117/feeds.json?api_key=ER2RW1ORI6791BT2')
        n_datos = lista_aleatorios.json()['channel']['last_entry_id']
        print('N elementos INTERNET: ' + str(n_datos))
        media = 0
        for i in range(n_datos):
            media = media + int(lista_aleatorios.json()['feeds'][i]['field1'])
        media = media/n_datos
        return render_template('index.html',msj=session['user'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']),media="Media BBDD internet: " + str(media))
    else:
        return render_template('index.html',msj="Media solo disponible para usuarios registrados")

@app.route('/umbral_historico',methods = ["POST"])
def umbral_historico():    # 5 últimos valores en los que se superó umbral
    if 'email' in session:      # Hay una sesión iniciada
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
        return render_template('index.html',msj=session['user'] + " está conectado",peticiones='Peticiones de media BBDD local: '+ str(session['peticiones']),umbral="Últimos 5 valores que han superado el umbral: " + str(lista_valores))
    else:
        return render_template('index.html',msj="Calculo umbral solo disponible para usuarios registrados")

@app.route('/graficas_externas',methods = ["POST"])
def graficas_externas():
    return render_template('graficas_externas.html')

if __name__ == "__main__":
    numero_global = 101
    hilo_n_aleatorio = threading.Thread(target=peticion_n_aleatorio, args=(120,numero_global))  # Peticion del numero cada 120s
    hilo_n_aleatorio.setDaemon(True) # Ejecucion sin bloquear hilo principal
    hilo_n_aleatorio.start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
