from flask import Flask, render_template



app = Flask(__name__)
import os

print("Carpeta actual:", os.getcwd())
print("Static:", app.static_folder)
print("Templates:", app.template_folder)



@app.route("/")
def inicio(): 
#main#
 return render_template("index.html")


#acerca de nosotros#
@app.route("/acerca--de--nosotros")
def acerca_de_nosotros():
    return render_template("acerca-de-nosotros.html")



@app.route("/asistente")
def asistente():
    return render_template("asistente_ai.html")


@app.route("/AI-worspase")
def hm():
    return render_template("hm.html")




if __name__ == "__main__":
 print("Iniciando servidor")
 app.run(debug=True)