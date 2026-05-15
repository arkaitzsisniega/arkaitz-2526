# Crono — feedback Arkaitz 16/5/2026 tarde

> Apuntado para no perder ninguna. Atacar **una por una**, cerrar al 100%
> antes de pasar a la siguiente.

## Lista (en orden de ataque)

- [ ] **1. Roja → auto-salida de pista + crono 2 min visible**
  - Cuando un jugador del INTER recibe roja estando en pista, sale
    inmediatamente. El slot queda vacío.
  - Crono regresivo 2 min visible para inferioridad (ya existe; verificar
    con nuevo flujo automático).
  - Cuando expulsan al RIVAL: crono regresivo de 2 min de superioridad
    (NUEVO). Banner verde paralelo al rojo.
- [ ] **2. Expulsado en banquillo → fuera de cualquier lista de cambio**
  - El jugador expulsado se queda visible en banquillo como "EXPULSADO"
    pero NO puede aparecer en ningún selector de cambio (ni manual ni
    rápido), ni en ChipsJugador, ni en otros modales.
- [ ] **3. Contraseña básica para el crono**
  - Auth simple "inter1977" (o configurable) que pide al entrar la primera
    vez. Sesión persistente en localStorage.
- [x] **4. (Ya hecho)** Tarjetas al rival con dorsal — funciona.
- [ ] **5. Colores progresivos en banquillo según fatiga residual**
  - Color de salida = color al final de su última rotación.
  - Cada minuto en banquillo, baja un nivel (rojo → naranja → verde → azul → gris).
  - Colores "light" (pasteles) para distinguirlos de los de pista.
- [ ] **6. Análisis profundo de datos disponibles**
  - Auditar TODO lo que el crono ya recopila (eventos, contadores, tiempos).
  - Identificar derivados que no estamos extrayendo aún:
    · Quinteto inicial 1T y 2T.
    · Zonas calientes de disparo (cuándo, desde dónde).
    · Cuartetos con mejor +/-.
    · Jugador con más asistencias a un goleador concreto.
    · Tiempo medio de rotación por jugador.
    · % efectividad disparos.
    · Etc.
  - Output: documento + (si procede) extender pestaña Resumen / nueva
    sección de "Análisis avanzado".

---

Filosofía: una tarea, profundizar, smoke + deploy + verificar.
