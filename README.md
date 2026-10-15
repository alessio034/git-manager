# Git Manager

Programa con interfaz gráfica para usar **Git** y subir tus proyectos a **GitHub**, **GitLab** o **Bitbucket** sin escribir comandos.

Es un solo archivo (`git_manager.pyw`): lo copias dentro de la carpeta de tu proyecto, le das doble clic y listo.

---

## Requisitos

| Requisito | Cómo comprobarlo | Dónde conseguirlo |
|---|---|---|
| Python 3.8 o superior | `python --version` | https://www.python.org/downloads/ (marca **"Add Python to PATH"** al instalar) |
| Git | `git --version` | https://git-scm.com |

No necesita instalar librerías adicionales: usa solo lo que trae Python.

---

## Inicio rápido

1. Copia `git_manager.pyw` dentro de la carpeta de tu proyecto:

   ```
   C:\mi-proyecto\
   ├── index.html
   ├── estilos.css
   └── git_manager.pyw   ← aquí
   ```

2. Haz **doble clic** en `git_manager.pyw`. El programa detecta automáticamente que esa carpeta es el proyecto.
3. Si la carpeta todavía no usa Git, pulsa **"Inicializar repositorio"**.
4. Agrega tu cuenta (te lo pedirá la primera vez que guardes cambios).
5. Conecta o crea el repositorio en la pestaña **Cuentas y repositorio**.
6. Escribe un mensaje y pulsa **"Subir"**. 🎉

> **El programa no se sube con tu proyecto.** Se excluye a sí mismo automáticamente (en `.git/info/exclude`, sin tocar tu `.gitignore`). Por eso, si lo abres en una carpeta donde solo está él, la lista de archivos aparece vacía.

---

## La ventana

### Cabecera

Muestra el nombre y la ruta del proyecto, y cuatro indicadores:

- **👤 Cuenta:** con qué cuenta trabajas en este proyecto. Haz clic para cambiarla.
- **Rama:** la rama en la que estás.
- **☁ Remoto:** a qué repositorio está conectado.
- **Estado:** cuántos cambios faltan por subir, o "Todo guardado".

Botones: **Ver en GitHub/GitLab/Bitbucket**, **Abrir carpeta** y **Cambiar proyecto**.

### Pestaña Cambios

- **Lista de archivos** con colores: 🟢 nuevo · 🟡 modificado · 🔴 eliminado · 🔵 renombrado.
- **Vista previa:** al seleccionar un archivo ves qué líneas se agregaron (verde) o quitaron (rojo).
- **Preparar / Preparar todos / Quitar:** eligen qué archivos entran en el próximo commit. También puedes hacer doble clic sobre un archivo para prepararlo.
- **Descartar:** deshace los cambios de los archivos seleccionados. ⚠️ No se puede deshacer.
- **Mensaje del commit:** describe brevemente qué cambiaste.
- **Guardar commit:** guarda una versión en tu computadora.
- **Subir:** prepara todo, hace el commit y lo sube, en un solo clic.
- **Subir a la rama:** elige a qué rama del remoto enviar. Puedes escribir un nombre nuevo para crearla. Si eliges una rama distinta a la tuya, te pide confirmación.
- **Traer:** descarga los cambios que haya en el remoto (`git pull`).

### Pestaña Historial

Todos los commits con código, mensaje, autor y fecha. Haz doble clic en uno para ver qué archivos cambió.

### Pestaña Ramas

Crear, cambiar, fusionar y eliminar ramas. Haz doble clic en una rama para cambiarte a ella.

### Pestaña Git Flow

Git Flow es una forma ordenada de trabajar con ramas: cada tipo de trabajo tiene su propia rama, así la versión publicada nunca se rompe mientras desarrollas.

| Rama | Para qué sirve | Sale de | Al terminar se fusiona en |
|---|---|---|---|
| `main` | La versión publicada (producción) | — | — |
| `develop` | Junta las funciones terminadas para la próxima versión | `main` | — |
| `feature/<nombre>` | Una función nueva | `develop` | `develop` |
| `release/<versión>` | Preparar una versión (últimos ajustes) | `develop` | `main` (con etiqueta) y `develop` |
| `hotfix/<versión>` | Arreglo urgente de lo publicado | `main` | `main` (con etiqueta) y `develop`* |

\* Si hay un release en curso, el hotfix se fusiona en ese release en lugar de `develop`.

En la pestaña:

- **Inicializar Git Flow:** crea `develop` a partir de tu rama principal y te cambia a ella.
- **＋ Feature / ＋ Release / ＋ Hotfix:** crea la rama desde su base. Para releases y hotfixes sugiere el siguiente número de versión según la última etiqueta.
- **✓ Terminar seleccionada:** hace las fusiones, crea la etiqueta de versión, borra la rama y ofrece subir todo a la plataforma. Si hay conflictos, resuélvelos, guarda un commit y vuelve a pulsar *Terminar*: continúa con los pasos que faltan.
- **⬆ Publicar:** sube la rama para que otras personas trabajen en ella.

**Ejemplo:**

1. **＋ Feature** `login` → crea `feature/login` desde `develop`.
2. Programas y guardas commits en la pestaña Cambios.
3. **✓ Terminar** → `feature/login` se fusiona en `develop` y se borra.
4. **＋ Release** `1.0.0` → crea `release/1.0.0` desde `develop`; corriges detalles.
5. **✓ Terminar** → se fusiona en `main`, se crea la etiqueta `1.0.0` y se fusiona en `develop`.
6. ¿Falló algo en producción? **＋ Hotfix** `1.0.1` desde `main`, lo arreglas y **✓ Terminar**.

> 💡 No necesitas instalar la extensión `git-flow`: el programa usa comandos normales de Git, pero guarda la configuración con las mismas claves (`gitflow.*`), así que puedes usar ambas en el mismo proyecto.

### Pestaña Cuentas y repositorio

- **Tus cuentas:** agrega, edita, elimina y elige la cuenta de este proyecto.
- **Crear repositorio nuevo:** lo crea en la plataforma de la cuenta elegida y conecta la carpeta automáticamente.
- **Conectar un repositorio que ya existe:** pega la URL (por ejemplo `https://github.com/usuario/proyecto.git`).

### Registro de comandos

En la parte inferior se ven todos los comandos de Git que ejecuta el programa y sus resultados. Sirve para aprender y para revisar errores.

---

## Varias cuentas

Puedes tener cuentas de distintas plataformas (por ejemplo "Personal" en GitHub y "Trabajo" en GitLab) y elegir una por proyecto.

Al elegir una cuenta, el programa configura **solo ese proyecto**:

- **Autor de los commits:** tu nombre y correo de esa cuenta.
- **Inicio de sesión:** le indica a Windows con qué usuario conectarse al subir.

La **primera vez** que subas con cada cuenta se abrirá una ventana para iniciar sesión en la plataforma. Después Windows la recuerda.

> 💡 Si tu navegador ya tiene abierta otra cuenta de la misma plataforma, cierra esa sesión o usa una ventana de incógnito al iniciar sesión. Si no, se puede guardar la cuenta equivocada.

### Datos de cada cuenta

| Campo | Para qué sirve |
|---|---|
| Apodo | Nombre para reconocerla ("Personal", "Trabajo") |
| Plataforma | GitHub, GitLab o Bitbucket |
| Servidor | Solo GitLab, si usas un servidor propio (por defecto `gitlab.com`) |
| Usuario | Tu usuario en la plataforma (no el correo) |
| Workspace | Solo Bitbucket: dónde se crean los repositorios (por defecto, tu usuario) |
| Nombre y correo | Aparecen como autor de tus commits |
| Token | Opcional. Solo hace falta para **crear repositorios** desde el programa |

### Cómo obtener un token

El formulario de la cuenta tiene un enlace **"Crear un token"** que abre la página correcta.

- **GitHub:** token clásico con el permiso `repo`.
- **GitLab:** token personal con el permiso `api`.
- **Bitbucket:** API token de Atlassian con permisos de repositorio. Se usa junto con el correo de tu cuenta Atlassian.

### Dónde se guardan

- Las cuentas se guardan en `%APPDATA%\GitManager\cuentas.json`, **fuera de tus proyectos**, así que nunca se suben por accidente.
- Los tokens van **cifrados** con tu usuario de Windows: otra persona u otra computadora no puede leerlos.
- Todas las copias del programa comparten las mismas cuentas, así que solo las agregas una vez.

---

## Atajos

| Tecla | Acción |
|---|---|
| `F5` | Refrescar |
| `Ctrl + Enter` | Guardar commit (con el cursor en el mensaje) |

La lista de cambios también se actualiza sola cuando vuelves a la ventana después de editar en tu editor.

---

## Qué hace cada botón por dentro

| Botón | Comando de Git |
|---|---|
| Inicializar repositorio | `git init -b main` |
| Preparar / Preparar todos | `git add <archivos>` / `git add -A` |
| Quitar | `git restore --staged <archivos>` |
| Guardar commit | `git commit -m "mensaje"` |
| Subir (misma rama) | `git add -A` → `git commit` → `git push -u origin <rama>` |
| Subir (otra rama) | `git push origin <tu-rama>:<rama-destino>` |
| Traer | `git pull --no-rebase origin <rama>` |
| Nueva rama / Cambiar | `git checkout -b <rama>` / `git checkout <rama>` |
| Fusionar | `git merge <rama>` |
| Git Flow: iniciar | `git checkout -b feature/<nombre> develop` (release desde `develop`, hotfix desde `main`) |
| Git Flow: terminar | `git merge --no-ff` en cada destino → `git tag -a <versión>` → `git branch -d <rama>` |
| Conectar repositorio | `git remote add origin <url>` |
| Usar cuenta | `git config --local user.name / user.email / credential.<servidor>.username` |

---

## Problemas frecuentes

**No aparecen archivos en la lista.**
La carpeta solo contiene el programa, que se excluye a sí mismo. Cópialo a la carpeta de un proyecto con archivos.

**"Carpeta no confiable" al abrir.**
Pasa con carpetas de otro usuario o en discos externos. Acepta el mensaje y el programa la marca como confiable.

**"Hay cambios nuevos" al subir.**
Alguien (o tú desde otra computadora) subió cambios que no tienes. Acepta traerlos y vuelve a pulsar **Subir**.

**Conflictos al traer o fusionar.**
Abre los archivos marcados, busca las marcas `<<<<<<<` y `>>>>>>>`, deja la versión correcta, borra las marcas y guarda un commit.

**No me deja cambiar de rama.**
Tienes cambios sin guardar. Haz un commit primero.

**Se subió con la cuenta equivocada o falla el inicio de sesión.**
Abre el **Administrador de credenciales** de Windows → *Credenciales de Windows*, borra las entradas que empiezan con `git:https://github.com` (o la plataforma que corresponda) y vuelve a subir para iniciar sesión de nuevo.

**Ver errores detallados.**
Revisa el **Registro de comandos** abajo. Si el programa no abre, ejecútalo desde una terminal con `python git_manager.pyw` para ver el error.

---

## `.pyw` vs `.py`

El archivo usa la extensión `.pyw` para que Windows lo abra **sin la ventana negra de consola**. El código es Python normal; si lo renombras a `.py` funciona igual, pero se verá la consola detrás.
