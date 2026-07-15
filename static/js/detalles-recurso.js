let modelo = document.getElementById("modelo");
let info = document.getElementById("info");

function mostrar(){

    let valor = modelo.value;

    if(valor === "flask"){

    info.innerHTML = "<h2>ANS Flask</h2>";

}
else if(valor === "gapi"){

    info.innerHTML = "<h2>ANS Gapi</h2>";

}
else if(valor === "codigo"){

    info.innerHTML = "<h2>Código modificable</h2>";

}
}





function mostrarDetalles(){

    const detalles = document.getElementById("detalles");
    const boton = document.getElementById("boton");

    detalles.classList.toggle("abierto");

    if(detalles.classList.contains("abierto")){
        boton.textContent = "Ocultar detalles";
    }else{
        boton.textContent = "Mostrar detalles";
    }

}



