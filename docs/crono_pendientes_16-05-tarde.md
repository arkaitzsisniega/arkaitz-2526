# Crono — feedback Arkaitz 16/5/2026 tarde

> Apuntado para no perder ninguna. Atacar **una por una**, cerrar al 100%
> antes de pasar a la siguiente.

## Lista (en orden de ataque) — ✅ TODO CERRADO

- [x] **1. Roja → auto-salida + crono superioridad rival** (commit 4db8bdd)
  - Helper expulsarJugadorInter centraliza la lógica. El jugador sale
    automáticamente del slot. Inferioridad ya existía; SUPERIORIDAD
    nueva (banner verde paralelo al rojo).
- [x] **2. Expulsado fuera de selectores** (commit 623ee7b)
  - `enPistaActivos` y `banquilloActivos` (sin expulsados) pasados a
    TODOS los modales. Queda visible en banquillo con badge rojo + EXPULSADO
    pero NO aparece en cambios, faltas, goles, amarillas, rojas, penaltis,
    disparo rival, tanda.
- [x] **3. Contraseña básica (inter1977)** (commit 4738eb9)
  - Componente AuthGate envuelve toda la app. SHA-256 del input vs
    constante PASS_HASH (no aparece en plano en el bundle).
    `localStorage.inter_crono_auth=1` persiste.
- [x] **4. (Ya hecho)** Tarjetas al rival con dorsal.
- [x] **5. Colores progresivos banquillo por fatiga residual** (commit 27fc4ac)
  - colorTiempoBanquillo(seg, segUltimoTurno) ahora calcula nivel
    inicial = nivel al salir de pista, y baja 1 nivel por minuto.
    Colores light/40 para distinguir visualmente de los de pista.
- [x] **6. Análisis profundo de datos** (commit f1c7f0e)
  - Doc auditoria docs/crono_datos_disponibles.md.
  - Nueva pestaña 🧠 Análisis en /resumen con 5 vistas:
    1) Quintetos iniciales por parte (derivados de eventos cambio).
    2) Asistencias por jugador + parejas más fluidas.
    3) Eficiencia ofensiva (% efectividad, % puntería).
    4) Cuartetos por +/- (top 5).
    5) Transiciones 20s (recup→gol nuestro, pérdida→gol rival).

---

**Cerrado: 6/6.** Lo que el user verá al refrescar el iPad:
- Banner verde de superioridad cuando expulsamos al rival.
- Roja saca al jugador automáticamente de pista (sin pasar por cambio manual).
- Expulsado no aparece en ningún selector (solo se ve en banquillo).
- Pantalla de login al entrar (pass: `inter1977`).
- Banquillo con colores light degradados según última rotación.
- Pestaña Análisis con métricas avanzadas en /resumen.
