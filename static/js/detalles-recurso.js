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

