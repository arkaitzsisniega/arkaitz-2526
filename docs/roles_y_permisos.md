# 🔐 Roles y permisos del dashboard

Sistema de auth con 4 roles que determina qué ve y qué puede hacer
cada usuario. Implementado en `dashboard/app.py`.

---

## Los 4 roles

| Rol | Quién | Qué ve / puede hacer |
|---|---|---|
| **👑 admin** | Tú (Arkaitz) | TODO. Único que puede editar partidos y scouting. Ve nombres reales en lesiones/temperatura. |
| **🧠 tecnico** | Cuerpo técnico (Pelu, Alex, Txubas…) | Lectura de TODAS las pestañas. NO puede editar partidos ni scouting. **Lesiones/Tratamientos/Temperatura: nombres ANONIMIZADOS por dorsal** ('el 8' en vez de 'RAYA'). |
| **🩹 fisio** | Jose, Miguel, Practicas | Lectura completa, incluyendo nombres reales en lesiones/temperatura (datos médicos). NO edita partidos. |
| **⚕️ medico** | Médico del equipo | Igual que fisio. |

---

## Cómo configurarlo

En **Streamlit Cloud → tu app → Settings → Secrets**, añade un bloque
así (al final del archivo, FUERA del `[gcp_service_account]`):

```toml
[APP_USERS]
"contraseña-de-arkaitz" = "admin"
"contraseña-cuerpo-tecnico" = "tecnico"
"contraseña-fisios" = "fisio"
"contraseña-medico" = "medico"
```

⚠️ **Importante**:
- Las contraseñas van entre **comillas dobles**.
- El rol va sin comillas (o con comillas, ambas valen) y debe ser uno
  de: `admin`, `tecnico`, `fisio`, `medico`.
- Mínimo 8 caracteres por seguridad. Algo memorable pero no obvio.
- Cada contraseña se reparte solo a las personas de ese rol.

### Modo legacy (1 sola contraseña, todos = admin)

Compatible hacia atrás:

```
APP_PASSWORD = "tu-contraseña"
```

Si solo defines `APP_PASSWORD` sin `APP_USERS`, todos los que entren
con esa contraseña son `admin`. Útil mientras montas el sistema.

### Tras editar Secrets

1. Pulsa **Save**.
2. **Reboot** la app (lista de apps → ⋮ tres puntos → Reboot).
3. Espera 30-60 segundos.
4. Abre el dashboard en pestaña **incógnito nueva** y prueba con cada
   contraseña.

---

## Qué ve cada rol en la práctica

### 👑 admin (tú)

- Todas las 17 pestañas visibles y funcionales.
- Botones "💾 Guardar partido / cambios / scouting" activos.
- Lesiones/Tratamientos/Temperatura: nombres reales.
- En la sidebar abajo: **"Tu sesión: 👑 ADMIN"**.

### 🧠 tecnico (cuerpo técnico)

- Pestaña "✏️ Editar partido" → **bloqueada** (ve un mensaje
  explicando que solo admin puede editar).
- Botón "💾 Guardar scouting" → ocultado.
- Lesiones/Tratamientos/Temperatura: jugadores aparecen como
  **"el N"** (donde N es su dorsal). Por ejemplo, si Raya (dorsal 8)
  tiene una lesión, el cuerpo técnico ve "el 8" en lugar de "RAYA".
- En sidebar: **"Tu sesión: 🧠 TECNICO"**.

### 🩹 fisio / ⚕️ medico

- Igual que tecnico EXCEPTO en Lesiones/Tratamientos/Temperatura,
  donde ven nombres reales (necesario para su trabajo médico).
- También ven "✏️ Editar partido" bloqueado y "💾 Guardar scouting"
  oculto (no editan partidos).

---

## Casos de uso típicos

### Compartir con el cuerpo técnico
1. Configura `[APP_USERS]` con 4 contraseñas distintas.
2. Manda al grupo de WhatsApp:
   - **Arkaitz**: contraseña-admin (te la guardas).
   - **Cuerpo técnico**: contraseña-tecnico.
   - **Fisios** (Jose, Miguel, Practicas): contraseña-fisios.
   - **Médico**: contraseña-medico (cuando lo añadas).

### Cambiar contraseña de un grupo (ej. alguien se va del cuerpo técnico)
1. Settings → Secrets → cambia el valor de la línea correspondiente.
2. Save → Reboot.
3. Comparte la nueva con los que SIGUEN.

### Si quieres ampliar a "jugador" en el futuro
Añadir a `ROLES_VALIDOS` el valor `"jugador"` y añadir la lógica
correspondiente (cada jugador solo se ve a sí mismo).

---

## Helpers disponibles en el código

```python
get_rol() -> str             # 'admin', 'tecnico', 'fisio', 'medico'
es_admin() -> bool
puede_editar_partidos() -> bool   # solo admin
ve_lesiones_completas() -> bool   # admin/fisio/medico (no tecnico)
anonimizar_nombre(jugador, dorsal) -> str   # 'RAYA', 8 → 'el 8'
anonimizar_df(df, col_jugador, col_dorsal) -> DataFrame
```

Si quieres añadir nuevas restricciones por pestaña, usa estos helpers
al inicio del bloque `with tab_X:`.

---

## Arquitectura

- `_leer_users_secret()`: lee `APP_USERS` de st.secrets, devuelve
  `dict[contraseña] = rol`. Compatible con `APP_PASSWORD` legacy.
- `_check_password()`: pantalla de login. Si la contraseña coincide
  con alguna entrada de APP_USERS, guarda el rol en
  `st.session_state["rol"]`.
- Helpers de permiso (`get_rol`, `es_admin`, etc.) consultan
  `st.session_state["rol"]`.
- Si no hay configuración, modo dev local con rol `admin` y warning
  visible.

---

## Privacidad de datos médicos

La anonimización por dorsal en lesiones/tratamientos/temperatura es
una práctica común para limitar el acceso a información médica
sensible al cuerpo médico-fisio que la necesita. El cuerpo técnico
puede saber que "el 8" se ha lesionado para gestión de minutos y
plantilla, pero la diagnóstico, tratamiento y detalles solo los ve
quien tiene relación directa con el cuidado del jugador.

Esto NO sustituye el consentimiento informado del jugador ni los
protocolos del club. Es una capa de seguridad adicional.
