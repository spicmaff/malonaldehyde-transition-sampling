document.querySelectorAll('[data-restart]').forEach(b=>b.addEventListener('click',()=>{const v=document.getElementById(b.dataset.restart);v.currentTime=0;v.play().catch(()=>{});}));
// Videos have native play/pause controls. No autoplay, sound or network access.
