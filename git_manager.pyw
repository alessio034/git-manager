"""
Git Manager - Interfaz grafica para usar Git y subir tu proyecto a GitHub, GitLab o Bitbucket.

Como usarlo:
  1. Copia este archivo dentro de la carpeta de tu proyecto (ej: C:/proyecto).
  2. Haz doble clic sobre el. Detecta automaticamente que esa carpeta es el proyecto .

Las cuentas se guardan en %APPDATA%/GitManager/cuentas.json (los tokens van cifrados
con tu usuario de Windows) y se comparten entre todas las copias del programa.

Requisitos: Python 3.8+ y Git instalado (https://git-scm.com). No necesita librerias extra.
"""

import base64
import json
import uuid
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# ---------------------------------------------------------------------- #
# Tema
# ---------------------------------------------------------------------- #
BG = "#16171d"
PANEL = "#1f2029"
CARD = "#282a36"
BORDE = "#3a3d4f"
TEXTO = "#e8e8f0"
TENUE = "#9095a8"
ACENTO = "#7c5cff"
VERDE = "#2fbf71"
ROJO = "#ff5c7a"
AMARILLO = "#f5c451"
AZUL = "#4aa3ff"

FUENTE = ("Segoe UI", 10)
FUENTE_B = ("Segoe UI", 10, "bold")
FUENTE_TITULO = ("Segoe UI", 18, "bold")
FUENTE_MONO = ("Consolas", 10)

SIN_VENTANA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

PLATAFORMAS = {
    "github": {
        "nombre": "GitHub",
        "servidor": "github.com",
        "token_url": "https://github.com/settings/tokens/new?scopes=repo&description=Git%20Manager",
        "token_ayuda": "Token clasico con el permiso 'repo'. Solo hace falta para crear repositorios "
                       "desde el programa; para subir cambios no se necesita.",
    },
    "gitlab": {
        "nombre": "GitLab",
        "servidor": "gitlab.com",
        "token_url": "https://{servidor}/-/user_settings/personal_access_tokens?name=Git%20Manager&scopes=api",
        "token_ayuda": "Token personal con el permiso 'api'. Solo hace falta para crear repositorios "
                       "desde el programa. Si usas un GitLab propio, cambia el servidor.",
    },
    "bitbucket": {
        "nombre": "Bitbucket",
        "servidor": "bitbucket.org",
        "token_url": "https://id.atlassian.com/manage-profile/security/api-tokens",
        "token_ayuda": "API token de Atlassian (elige Bitbucket y los permisos de repositorio). Se usa "
                       "junto con el correo de tu cuenta Atlassian. El workspace es donde se crean "
                       "los repositorios (si lo dejas vacio se usa tu usuario).",
    },
}

CARPETA_CONFIG = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "GitManager")
ARCHIVO_CUENTAS = os.path.join(CARPETA_CONFIG, "cuentas.json")


def carpeta_del_programa():
    """La carpeta del proyecto es donde esta guardado este archivo."""
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        return os.path.abspath(sys.argv[1])
    if getattr(sys, "frozen", False):  # empaquetado como .exe
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def aclarar(color, factor=0.12):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * factor) for c in (r, g, b))


def url_web(remoto):
    """Convierte la URL del remoto en una direccion web (sin credenciales ni .git)."""
    url = remoto.strip()
    m = re.match(r"git@([^:]+):(.+)", url)
    if m:
        url = f"https://{m.group(1)}/{m.group(2)}"
    url = re.sub(r"https?://[^/@]+@", "https://", url)
    return url[:-4] if url.endswith(".git") else url


def host_de(url):
    """Servidor de una URL de git: https://usuario@github.com/a/b.git o git@github.com:a/b.git"""
    m = re.match(r"(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)", url.strip(), re.I)
    return m.group(1).lower() if m else ""


def plataforma_de_host(host):
    for clave, datos in PLATAFORMAS.items():
        if host == datos["servidor"]:
            return clave
    return "gitlab" if "gitlab" in host else None


def servidor_de(cuenta):
    return cuenta.get("servidor") or PLATAFORMAS[cuenta["plataforma"]]["servidor"]


# ---------------------------------------------------------------------- #
# Cuentas (guardadas fuera del proyecto, tokens cifrados con DPAPI de Windows)
# ---------------------------------------------------------------------- #
if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _dpapi(datos, cifrar_):
        buffer = ctypes.create_string_buffer(datos, len(datos))
        entrada = _Blob(len(datos), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        salida = _Blob()
        funcion = ctypes.windll.crypt32.CryptProtectData if cifrar_ else ctypes.windll.crypt32.CryptUnprotectData
        if not funcion(ctypes.byref(entrada), None, None, None, None, 0x1, ctypes.byref(salida)):
            raise OSError("No se pudo cifrar/descifrar el token")
        try:
            return ctypes.string_at(salida.pbData, salida.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def cifrar(texto):
    if not texto:
        return ""
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_dpapi(texto.encode(), True)).decode()
    return "b64:" + base64.b64encode(texto.encode()).decode()  # fuera de Windows: solo ofuscado


def descifrar(texto):
    try:
        if texto.startswith("dpapi:") and os.name == "nt":
            return _dpapi(base64.b64decode(texto[6:]), False).decode()
        if texto.startswith("b64:"):
            return base64.b64decode(texto[4:]).decode()
    except (OSError, ValueError):
        pass
    return ""


def cargar_cuentas():
    try:
        with open(ARCHIVO_CUENTAS, encoding="utf-8") as f:
            return [c for c in json.load(f).get("cuentas", []) if c.get("plataforma") in PLATAFORMAS]
    except (OSError, ValueError):
        return []


def guardar_cuentas(cuentas):
    os.makedirs(CARPETA_CONFIG, exist_ok=True)
    temporal = ARCHIVO_CUENTAS + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump({"cuentas": cuentas}, f, indent=2, ensure_ascii=False)
    os.replace(temporal, ARCHIVO_CUENTAS)


def describir(xy):
    if xy == "??":
        return "Nuevo", "nuevo"
    if "U" in xy or xy in ("AA", "DD"):
        return "Conflicto", "conflicto"
    letra = xy[0] if xy[0] != " " else xy[1]
    return {
        "M": ("Modificado", "mod"),
        "A": ("Agregado", "nuevo"),
        "D": ("Eliminado", "borrado"),
        "R": ("Renombrado", "renombrado"),
        "C": ("Copiado", "renombrado"),
        "T": ("Cambio de tipo", "mod"),
    }.get(letra, (xy.strip(), "mod"))


# ---------------------------------------------------------------------- #
# Git
# ---------------------------------------------------------------------- #
class Git:
    def __init__(self, ruta, salida):
        self.ruta = ruta
        self.salida = salida  # cola de mensajes para el registro

    def run(self, *args, silencioso=False):
        if not silencioso:
            self.salida.put(("$ git " + " ".join(f'"{a}"' if " " in a else a for a in args), "cmd"))
        r = subprocess.run(
            ["git", *args],
            cwd=self.ruta,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            creationflags=SIN_VENTANA,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if not silencioso:
            texto = (r.stdout + r.stderr).strip()
            if texto:
                self.salida.put((texto, "salida" if r.returncode == 0 else "error"))
        return r.returncode, r.stdout, r.stderr

    def es_repo(self):
        return self.run("rev-parse", "--is-inside-work-tree", silencioso=True)[0] == 0

    def raiz(self):
        c, o, _ = self.run("rev-parse", "--show-toplevel", silencioso=True)
        return os.path.normpath(o.strip()) if c == 0 else None

    def rama(self):
        return self.run("branch", "--show-current", silencioso=True)[1].strip()

    def tiene_commits(self):
        return self.run("rev-parse", "--verify", "-q", "HEAD", silencioso=True)[0] == 0

    def remoto(self):
        c, o, _ = self.run("remote", "get-url", "origin", silencioso=True)
        return o.strip() if c == 0 else ""

    def config(self, clave):
        return self.run("config", clave, silencioso=True)[1].strip()

    def ramas(self):
        o = self.run("branch", "--format=%(refname:short)", silencioso=True)[1]
        return [l.strip() for l in o.splitlines() if l.strip()]

    def ramas_remotas(self):
        """Ramas que existen en el remoto (segun la ultima vez que se hablo con el)."""
        o = self.run("branch", "-r", "--format=%(refname:short)", silencioso=True)[1]
        return [l.strip()[len("origin/"):] for l in o.splitlines()
                if l.strip().startswith("origin/") and l.strip() != "origin/HEAD"]

    def nombre_rama_valido(self, nombre):
        return self.run("check-ref-format", "--branch", nombre, silencioso=True)[0] == 0

    def historial(self, n=200):
        c, o, _ = self.run(
            "log", f"-n{n}", "--date=format:%d/%m/%Y %H:%M",
            "--pretty=format:%h%x1f%s%x1f%an%x1f%ad", silencioso=True,
        )
        if c:
            return []
        return [l.split("\x1f") for l in o.splitlines() if l.count("\x1f") == 3]

    def estado(self):
        c, o, _ = self.run("status", "--porcelain=v1", "-z", "-uall", silencioso=True)
        if c:
            return []
        partes, i, res = o.split("\0"), 0, []
        while i < len(partes):
            entrada = partes[i]
            i += 1
            if len(entrada) < 4:
                continue
            xy, archivo = entrada[:2], entrada[3:]
            if xy[0] in "RC":
                i += 1  # el nombre original viene a continuacion
            res.append((xy, archivo))
        return res


class ErrorPlataforma(Exception):
    def __init__(self, codigo, detalle):
        super().__init__(codigo)
        self.codigo, self.detalle = codigo, detalle


def _post_json(url, datos, cabeceras, plataforma):
    peticion = urllib.request.Request(
        url, data=json.dumps(datos).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "git-manager-python", **cabeceras},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detalle = json.load(e)
        except Exception:
            detalle = {}
        raise ErrorPlataforma(e.code, detalle)
    except urllib.error.URLError:
        raise RuntimeError(f"No se pudo conectar con {plataforma}. Revisa tu conexion a internet.")


def crear_repositorio(cuenta, nombre, descripcion, privado):
    """Crea el repositorio con la API de la plataforma. Devuelve (url_web, url_para_git)."""
    clave = cuenta["plataforma"]
    plataforma = PLATAFORMAS[clave]["nombre"]
    token = descifrar(cuenta.get("token", ""))
    if not token and clave == "github":
        token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError(f"La cuenta '{cuenta['apodo']}' no tiene token.\n\n"
                           "Editala en la pestaña 'Cuentas y repositorio' para agregarlo.")
    try:
        if clave == "github":
            r = _post_json("https://api.github.com/user/repos",
                           {"name": nombre, "description": descripcion, "private": privado},
                           {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                           plataforma)
            return r["html_url"], r["clone_url"]
        if clave == "gitlab":
            r = _post_json(f"https://{servidor_de(cuenta)}/api/v4/projects",
                           {"name": nombre, "description": descripcion,
                            "visibility": "private" if privado else "public"},
                           {"PRIVATE-TOKEN": token}, plataforma)
            return r["web_url"], r["http_url_to_repo"]
        # Bitbucket: autenticacion basica con correo de Atlassian + API token
        workspace = cuenta.get("workspace") or cuenta["usuario"]
        slug = re.sub(r"[^a-z0-9_.-]+", "-", nombre.lower()).strip("-")
        basica = base64.b64encode(f"{cuenta['email']}:{token}".encode()).decode()
        r = _post_json(f"https://api.bitbucket.org/2.0/repositories/{workspace}/{slug}",
                       {"scm": "git", "is_private": privado, "description": descripcion},
                       {"Authorization": f"Basic {basica}"}, plataforma)
        clonar = next(c["href"] for c in r["links"]["clone"] if c["name"] == "https")
        return r["links"]["html"]["href"], re.sub(r"^https://[^/@]+@", "https://", clonar)
    except ErrorPlataforma as e:
        texto = json.dumps(e.detalle).lower()
        if e.codigo == 401:
            raise RuntimeError(f"{plataforma} rechazo el token: no es valido o ya expiro.")
        if e.codigo == 403:
            raise RuntimeError(f"El token no tiene permiso para crear repositorios en {plataforma}.")
        if "already" in texto or "taken" in texto:
            raise RuntimeError(f"Ya existe un repositorio llamado '{nombre}' en tu cuenta de {plataforma}.")
        raise RuntimeError(f"{plataforma} respondio con error {e.codigo}:\n{json.dumps(e.detalle)[:400]}")


# ---------------------------------------------------------------------- #
# Widgets
# ---------------------------------------------------------------------- #
def boton(padre, texto, comando, color=CARD, fg=TEXTO, grande=False):
    hover = aclarar(color)
    b = tk.Button(
        padre, text=texto, command=comando, bg=color, fg=fg,
        activebackground=hover, activeforeground=fg, disabledforeground=TENUE,
        relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        font=("Segoe UI", 12, "bold") if grande else FUENTE_B,
        padx=24 if grande else 14, pady=12 if grande else 6,
    )
    b.bind("<Enter>", lambda e: b["state"] == "normal" and b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


def entrada(padre, show=""):
    return tk.Entry(
        padre, bg=CARD, fg=TEXTO, insertbackground=TEXTO, relief="flat", font=FUENTE,
        highlightthickness=1, highlightbackground=BORDE, highlightcolor=ACENTO, show=show,
    )


def poner(campo, valor):
    campo.delete(0, "end")
    campo.insert(0, valor)


class DialogoCuenta(tk.Toplevel):
    """Ventana para agregar o editar una cuenta. Deja el resultado en self.resultado."""

    def __init__(self, padre, cuenta=None):
        super().__init__(padre)
        self.cuenta = cuenta or {}
        self.resultado = None
        titulo = "Editar cuenta" if cuenta else "Agregar cuenta"
        self.title(titulo)
        self.configure(bg=PANEL, padx=24, pady=20)
        self.resizable(False, False)
        self.transient(padre)
        self.columnconfigure(1, weight=1, minsize=320)

        tk.Label(self, text=titulo, bg=PANEL, fg=TEXTO, font=("Segoe UI", 14, "bold")
                 ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.filas = {}
        c = self.cuenta
        self._campo("apodo", "Apodo", 1, c.get("apodo", ""), "Ej: Personal, Trabajo")

        tk.Label(self, text="Plataforma", bg=PANEL, fg=TENUE).grid(row=2, column=0, sticky="w", pady=4)
        self.var_plat = tk.StringVar(value=PLATAFORMAS[c.get("plataforma", "github")]["nombre"])
        marco = tk.Frame(self, bg=PANEL)
        marco.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Combobox(marco, textvariable=self.var_plat, state="readonly", font=FUENTE,
                     values=[p["nombre"] for p in PLATAFORMAS.values()]).pack(side="left", fill="x", expand=True)
        tk.Label(marco, bg=PANEL, width=20).pack(side="left", padx=(10, 0))

        self._campo("servidor", "Servidor", 3, c.get("servidor", "gitlab.com"), "Solo GitLab propio")
        self._campo("usuario", "Usuario", 4, c.get("usuario", ""), "Tu usuario, no el correo")
        self._campo("workspace", "Workspace", 5, c.get("workspace", ""), "Opcional")
        self._campo("nombre", "Nombre", 6, c.get("nombre", ""), "Autor de los commits")
        self._campo("email", "Correo", 7, c.get("email", ""), "El de tu cuenta")
        self._campo("token", "Token", 8, descifrar(c.get("token", "")), "Opcional", show="•")

        self.lbl_ayuda = tk.Label(self, bg=PANEL, fg=TENUE, wraplength=420, justify="left")
        self.lbl_ayuda.grid(row=9, column=1, sticky="w", pady=(2, 0))
        self.enlace = tk.Label(self, bg=PANEL, fg=AZUL, cursor="hand2", text="Crear un token ↗")
        self.enlace.grid(row=10, column=1, sticky="w")
        self.enlace.bind("<Button-1>", lambda e: webbrowser.open(self._url_token()))

        botones = tk.Frame(self, bg=PANEL)
        botones.grid(row=11, column=0, columnspan=2, sticky="e", pady=(18, 0))
        boton(botones, "Cancelar", self.destroy).pack(side="left", padx=(0, 8))
        boton(botones, "Guardar cuenta", self._guardar, ACENTO, fg="white").pack(side="left")

        self.var_plat.trace_add("write", lambda *a: self._actualizar())
        self._actualizar()
        self.bind("<Return>", lambda e: self._guardar())
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        x = padre.winfo_rootx() + (padre.winfo_width() - self.winfo_width()) // 2
        y = padre.winfo_rooty() + (padre.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.filas["apodo"][1].focus_set()

    def _campo(self, clave, etiqueta, fila, valor, pista, show=""):
        lbl = tk.Label(self, text=etiqueta, bg=PANEL, fg=TENUE)
        lbl.grid(row=fila, column=0, sticky="w", padx=(0, 14), pady=4)
        marco = tk.Frame(self, bg=PANEL)
        marco.grid(row=fila, column=1, sticky="ew", pady=4)
        e = entrada(marco, show)
        e.insert(0, valor)
        e.pack(side="left", fill="x", expand=True, ipady=5)
        tk.Label(marco, text=pista, bg=PANEL, fg=TENUE, width=20, anchor="w").pack(side="left", padx=(10, 0))
        self.filas[clave] = (lbl, e, marco)

    def _plataforma(self):
        return next(k for k, p in PLATAFORMAS.items() if p["nombre"] == self.var_plat.get())

    def _url_token(self):
        servidor = self.filas["servidor"][1].get().strip() or "gitlab.com"
        return PLATAFORMAS[self._plataforma()]["token_url"].format(servidor=servidor)

    def _actualizar(self):
        clave = self._plataforma()
        for campo, visible in (("servidor", clave == "gitlab"), ("workspace", clave == "bitbucket")):
            lbl, _, marco = self.filas[campo]
            for w in (lbl, marco):
                w.grid() if visible else w.grid_remove()
        self.lbl_ayuda.config(text=PLATAFORMAS[clave]["token_ayuda"])

    def _guardar(self):
        valores = {k: fila[1].get().strip() for k, fila in self.filas.items()}
        faltan = [n for k, n in (("apodo", "Apodo"), ("usuario", "Usuario"),
                                 ("nombre", "Nombre"), ("email", "Correo")) if not valores[k]]
        if faltan:
            messagebox.showwarning("Faltan datos", "Completa: " + ", ".join(faltan), parent=self)
            return
        clave = self._plataforma()
        servidor = PLATAFORMAS[clave]["servidor"]
        if clave == "gitlab":
            servidor = re.sub(r"^https?://", "", valores["servidor"]).strip("/") or servidor
        self.resultado = {
            "id": self.cuenta.get("id") or uuid.uuid4().hex,
            "apodo": valores["apodo"],
            "plataforma": clave,
            "servidor": servidor,
            "usuario": valores["usuario"],
            "workspace": valores["workspace"] if clave == "bitbucket" else "",
            "nombre": valores["nombre"],
            "email": valores["email"],
            "token": cifrar(valores["token"]),
        }
        self.destroy()


# ---------------------------------------------------------------------- #
# Aplicacion
# ---------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self, ruta):
        super().__init__()
        self.title("Git Manager")
        self.configure(bg=BG)
        self.geometry("1180x780")
        self.minsize(980, 660)
        self.report_callback_exception = self._error_inesperado

        self.cola = queue.Queue()
        self.git = Git(ruta, self.cola)
        self.ocupado = False
        self.estados = {}
        self.remotas = set()
        self.cuentas = cargar_cuentas()
        self.plat = "GitHub"  # nombre de la plataforma del remoto, para los textos
        self.modo_repo = None
        self.ultimo_refresco = 0
        self.id_aviso = None

        self._estilos()
        self._construir()
        self.bind("<F5>", lambda e: self.refrescar())
        self.bind("<FocusIn>", self._al_enfocar)
        self.after(100, self._leer_cola)
        self.cambiar_proyecto(ruta)

    # ----------------------------- Estilos ---------------------------- #
    def _estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXTO, font=FUENTE, borderwidth=0)
        s.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG,
                    lightcolor=BG, darkcolor=BG, tabmargins=(0, 0, 0, 0))
        s.configure("TNotebook.Tab", background=PANEL, foreground=TENUE, padding=(18, 9),
                    font=FUENTE_B, borderwidth=0, bordercolor=BG, lightcolor=PANEL, focuscolor=PANEL)
        s.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXTO)],
              lightcolor=[("selected", CARD)], focuscolor=[("selected", CARD)])
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXTO,
                    rowheight=28, borderwidth=0, font=FUENTE)
        s.configure("Treeview.Heading", background=PANEL, foreground=TENUE, font=FUENTE_B,
                    borderwidth=0, padding=(8, 6), relief="flat")
        s.map("Treeview.Heading", background=[("active", BORDE)])
        s.map("Treeview", background=[("selected", ACENTO)], foreground=[("selected", "#ffffff")])
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Vertical.TScrollbar", background=BORDE, troughcolor=CARD, bordercolor=CARD,
                    arrowcolor=TENUE, lightcolor=BORDE, darkcolor=BORDE, gripcount=0)
        s.map("Vertical.TScrollbar", background=[("active", aclarar(BORDE)), ("disabled", CARD)],
              arrowcolor=[("disabled", CARD)])
        s.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXTO,
                    arrowcolor=TEXTO, bordercolor=BORDE, lightcolor=CARD, darkcolor=CARD,
                    insertcolor=TEXTO, padding=(8, 5))
        s.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", TEXTO)],
              bordercolor=[("focus", ACENTO)], background=[("active", BORDE)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", FUENTE)
        s.configure("Horizontal.TProgressbar", background=ACENTO, troughcolor=CARD,
                    bordercolor=PANEL, lightcolor=ACENTO, darkcolor=ACENTO)

    # ----------------------------- Interfaz --------------------------- #
    def _construir(self):
        # Cabecera
        cab = tk.Frame(self, bg=PANEL, padx=24, pady=16)
        cab.pack(fill="x")
        der = tk.Frame(cab, bg=PANEL)  # se empaqueta primero para que nunca se recorte
        der.pack(side="right", anchor="n")
        izq = tk.Frame(cab, bg=PANEL)
        izq.pack(side="left", fill="x", expand=True)
        self.lbl_nombre = tk.Label(izq, bg=PANEL, fg=TEXTO, font=FUENTE_TITULO, anchor="w")
        self.lbl_nombre.pack(fill="x")
        self.lbl_ruta = tk.Label(izq, bg=PANEL, fg=TENUE, anchor="w")
        self.lbl_ruta.pack(fill="x")
        chips = tk.Frame(izq, bg=PANEL)
        chips.pack(anchor="w", pady=(10, 0))
        self.chip_cuenta, self.chip_rama, self.chip_remoto, self.chip_cambios = (
            tk.Label(chips, bg=CARD, fg=TEXTO, padx=10, pady=4) for _ in range(4)
        )
        for chip in (self.chip_cuenta, self.chip_rama, self.chip_remoto, self.chip_cambios):
            chip.pack(side="left", padx=(0, 8))
        # El chip de la cuenta funciona como boton: abre el menu para cambiar de cuenta
        self.chip_cuenta.config(cursor="hand2", bg=aclarar(CARD, 0.06))
        self.chip_cuenta.bind("<Button-1>", self._menu_cuentas)
        self.chip_cuenta.bind("<Enter>", lambda e: self.chip_cuenta.config(bg=BORDE))
        self.chip_cuenta.bind("<Leave>", lambda e: self.chip_cuenta.config(bg=aclarar(CARD, 0.06)))

        self.btn_github = boton(der, "Ver en la web  ↗", self.abrir_github)
        self.btn_github.pack(side="left", padx=4)
        boton(der, "Abrir carpeta", self.abrir_carpeta).pack(side="left", padx=4)
        boton(der, "Cambiar proyecto", self.elegir_proyecto).pack(side="left", padx=4)

        # Barra de estado
        barra = tk.Frame(self, bg=PANEL, padx=16, pady=6)
        barra.pack(side="bottom", fill="x")
        self.lbl_estado = tk.Label(barra, text="Listo", bg=PANEL, fg=TENUE, anchor="w")
        self.lbl_estado.pack(side="left", fill="x", expand=True)
        tk.Label(barra, text="F5 = refrescar   ·   Ctrl+Enter = guardar commit",
                 bg=PANEL, fg=TENUE).pack(side="right", padx=(12, 0))
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=140)  # visible solo trabajando

        # Cuerpo (contenido arriba, registro abajo, con divisor arrastrable)
        div = tk.PanedWindow(self, orient="vertical", bg=BG, sashwidth=8, bd=0)
        div.pack(fill="both", expand=True, padx=16, pady=(10, 6))
        self.contenedor = tk.Frame(div, bg=BG)
        div.add(self.contenedor, stretch="always", minsize=320)
        div.add(self._panel_registro(div), stretch="never", minsize=80, height=140)

        self.notebook = ttk.Notebook(self.contenedor)
        self._tab_cambios()
        self._tab_historial()
        self._tab_ramas()
        self._tab_cuentas()
        self.vacio = self._panel_vacio(self.contenedor)

    def _arbol(self, padre, columnas, seleccion="extended"):
        marco = tk.Frame(padre, bg=CARD)
        marco.pack(fill="both", expand=True)
        arbol = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings",
                             selectmode=seleccion)
        for clave, titulo, ancho, estira in columnas:
            arbol.heading(clave, text=titulo, anchor="w")
            arbol.column(clave, width=ancho, stretch=estira, anchor="w")
        sb = ttk.Scrollbar(marco, orient="vertical", command=arbol.yview)
        arbol.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        arbol.pack(fill="both", expand=True, padx=(6, 0), pady=6)
        return arbol

    def _texto(self, padre, wrap="none", **kw):
        marco = tk.Frame(padre, bg=CARD)
        marco.pack(fill="both", expand=True)
        txt = tk.Text(marco, bg=CARD, fg=TEXTO, font=FUENTE_MONO, relief="flat", bd=0,
                      highlightthickness=0, padx=12, pady=10, wrap=wrap,
                      insertbackground=TEXTO, state="disabled", **kw)
        sb = ttk.Scrollbar(marco, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        return txt

    def _tab_cambios(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text="  Cambios  ")

        # Tarjeta de commit (abajo)
        card = tk.Frame(tab, bg=PANEL, padx=16, pady=14)
        card.pack(side="bottom", fill="x", pady=(12, 0))
        card.columnconfigure(0, weight=1)
        tk.Label(card, text="Mensaje del commit", bg=PANEL, fg=TEXTO, font=FUENTE_B
                 ).grid(row=0, column=0, sticky="w")
        tk.Label(card, text="Describe brevemente que cambiaste. Ej: \"Agrego la pagina de contacto\"",
                 bg=PANEL, fg=TENUE).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.txt_msg = tk.Text(card, height=2, bg=CARD, fg=TEXTO, font=FUENTE, relief="flat",
                               insertbackground=TEXTO, highlightthickness=1, wrap="word",
                               highlightbackground=BORDE, highlightcolor=ACENTO, padx=10, pady=8)
        self.txt_msg.grid(row=2, column=0, sticky="ew")
        self.txt_msg.bind("<Control-Return>", lambda e: (self.commit(), "break")[1])

        botones = tk.Frame(card, bg=PANEL)
        botones.grid(row=0, column=1, rowspan=3, sticky="nse", padx=(16, 0))
        boton(botones, "✓  Guardar commit", self.commit, ACENTO, fg="white"
              ).grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        self.btn_traer = boton(botones, "⬇  Traer de GitHub", self.traer, CARD)
        self.btn_traer.grid(row=1, column=0, sticky="ew", padx=4, pady=3)
        self.btn_subir = boton(botones, "⬆  Subir a GitHub", self.subir, VERDE, fg="white", grande=True)
        self.btn_subir.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=4, pady=3)

        # Selector de rama destino en el remoto (se puede escribir un nombre nuevo)
        destino = tk.Frame(botones, bg=PANEL)
        destino.grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
        tk.Label(destino, text="Subir a la rama:", bg=PANEL, fg=TENUE).pack(side="left", padx=(0, 8))
        self.var_destino = tk.StringVar()
        self.cmb_destino = ttk.Combobox(destino, textvariable=self.var_destino, font=FUENTE)
        self.cmb_destino.pack(side="left", fill="x", expand=True)
        self.lbl_destino = tk.Label(botones, bg=PANEL, fg=TENUE, anchor="w")
        self.lbl_destino.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4)
        self.var_destino.trace_add("write", lambda *a: self._describir_destino())
        self.rama_mostrada = None

        div = tk.PanedWindow(tab, orient="horizontal", bg=BG, sashwidth=8, bd=0)
        div.pack(fill="both", expand=True, pady=(10, 0))

        # Lista de archivos
        izq = tk.Frame(div, bg=BG)
        acciones = tk.Frame(izq, bg=BG)
        acciones.pack(side="bottom", fill="x", pady=(8, 0))
        boton(acciones, "＋ Preparar", self.preparar_seleccion).pack(side="left", padx=(0, 6))
        boton(acciones, "＋ Preparar todos", self.preparar_todos).pack(side="left", padx=(0, 6))
        boton(acciones, "－ Quitar", self.quitar_seleccion).pack(side="left", padx=(0, 6))
        boton(acciones, "✕ Descartar", self.descartar, CARD, fg=ROJO).pack(side="left")
        enc = tk.Frame(izq, bg=BG)
        enc.pack(fill="x", pady=(0, 6))
        tk.Label(enc, text="Archivos con cambios", bg=BG, fg=TEXTO, font=FUENTE_B).pack(side="left")
        self.lbl_conteo = tk.Label(enc, bg=BG, fg=TENUE)
        self.lbl_conteo.pack(side="left", padx=6)
        self.arbol = self._arbol(izq, [("archivo", "Archivo", 320, True),
                                       ("estado", "Estado", 110, False),
                                       ("prep", "Preparado", 90, False)])
        for tag, color in (("nuevo", VERDE), ("mod", AMARILLO), ("borrado", ROJO),
                           ("renombrado", AZUL), ("conflicto", ROJO)):
            self.arbol.tag_configure(tag, foreground=color)
        self.arbol.bind("<<TreeviewSelect>>", self._previsualizar)
        self.arbol.bind("<Double-1>", lambda e: self.preparar_seleccion())
        div.add(izq, minsize=420, width=600, stretch="always")

        # Vista previa
        der = tk.Frame(div, bg=BG)
        tk.Label(der, text="Vista previa del cambio", bg=BG, fg=TEXTO, font=FUENTE_B
                 ).pack(anchor="w", pady=(0, 6))
        self.txt_diff = self._texto(der)
        self.txt_diff.tag_configure("add", foreground=VERDE)
        self.txt_diff.tag_configure("del", foreground=ROJO)
        self.txt_diff.tag_configure("hunk", foreground=AZUL)
        self.txt_diff.tag_configure("meta", foreground=TENUE)
        div.add(der, minsize=260, stretch="always")

    def _tab_historial(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text="  Historial  ")
        tk.Label(tab, text="Doble clic sobre un commit para ver los archivos que cambio.",
                 bg=BG, fg=TENUE).pack(anchor="w", pady=(10, 6))
        self.arbol_log = self._arbol(tab, [("hash", "Codigo", 90, False),
                                           ("mensaje", "Mensaje", 500, True),
                                           ("autor", "Autor", 170, False),
                                           ("fecha", "Fecha", 140, False)], "browse")
        self.arbol_log.bind("<Double-1>", self._ver_commit)

    def _tab_ramas(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text="  Ramas  ")
        lado = tk.Frame(tab, bg=BG, padx=16)
        lado.pack(side="right", fill="y", pady=(10, 0))
        tk.Label(lado, text="Las ramas te permiten probar\ncambios sin afectar la principal.",
                 bg=BG, fg=TENUE, justify="left").pack(anchor="w", pady=(0, 12))
        for texto, cmd, color in (("＋ Nueva rama", self.nueva_rama, ACENTO),
                                  ("⇄ Cambiar a esta rama", self.cambiar_rama, CARD),
                                  ("⤵ Fusionar en la actual", self.fusionar_rama, CARD),
                                  ("✕ Eliminar rama", self.eliminar_rama, CARD)):
            boton(lado, texto, cmd, color, fg="white" if color == ACENTO else TEXTO
                  ).pack(fill="x", pady=3)
        cont = tk.Frame(tab, bg=BG)
        cont.pack(fill="both", expand=True, pady=(10, 0))
        self.arbol_ramas = self._arbol(cont, [("rama", "Rama", 300, True),
                                              ("estado", "", 140, False)], "browse")
        self.arbol_ramas.tag_configure("actual", foreground=VERDE)
        self.arbol_ramas.bind("<Double-1>", lambda e: self.cambiar_rama())

    def _tarjeta(self, padre, titulo, subtitulo):
        card = tk.Frame(padre, bg=PANEL, padx=18, pady=14)
        tk.Label(card, text=titulo, bg=PANEL, fg=TEXTO, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        card.subtitulo = tk.Label(card, text=subtitulo, bg=PANEL, fg=TENUE, justify="left", wraplength=440)
        card.subtitulo.pack(anchor="w", pady=(0, 10))
        card.cuerpo = tk.Frame(card, bg=PANEL)
        card.cuerpo.pack(fill="x")
        card.cuerpo.columnconfigure(1, weight=1)
        return card

    def _campo(self, cuerpo, etiqueta, fila, show=""):
        tk.Label(cuerpo, text=etiqueta, bg=PANEL, fg=TENUE).grid(row=fila, column=0, sticky="w",
                                                                 padx=(0, 12), pady=4)
        e = entrada(cuerpo, show)
        e.grid(row=fila, column=1, sticky="ew", pady=4, ipady=5)
        return e

    def _check(self, padre, texto, variable):
        return tk.Checkbutton(padre, text=texto, variable=variable, bg=PANEL, fg=TEXTO,
                              selectcolor=CARD, activebackground=PANEL, activeforeground=TEXTO,
                              bd=0, highlightthickness=0, cursor="hand2")

    def _tab_cuentas(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text="  Cuentas y repositorio  ")
        self.tab_cuentas = tab
        tab.columnconfigure(0, weight=1, uniform="c")
        tab.columnconfigure(1, weight=1, uniform="c")

        # Cuentas guardadas (compartidas por todas las copias del programa)
        c1 = self._tarjeta(tab, "Tus cuentas",
                           "GitHub, GitLab o Bitbucket. Elige cual usar en este proyecto: define el autor "
                           "de los commits y con que cuenta se inicia sesion al subir.")
        c1.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8), pady=(10, 8))
        acciones = tk.Frame(c1.cuerpo, bg=PANEL)
        acciones.pack(side="bottom", fill="x", pady=(8, 0))
        boton(acciones, "＋ Agregar", self.agregar_cuenta).pack(side="left", padx=(0, 6))
        boton(acciones, "Editar", self.editar_cuenta).pack(side="left", padx=(0, 6))
        boton(acciones, "Eliminar", self.eliminar_cuenta, CARD, fg=ROJO).pack(side="left")
        boton(acciones, "✓ Usar en este proyecto", self.usar_cuenta_seleccionada, ACENTO, fg="white"
              ).pack(side="right")
        self.arbol_cuentas = self._arbol(c1.cuerpo, [("apodo", "Apodo", 130, True),
                                                     ("plataforma", "Plataforma", 100, False),
                                                     ("usuario", "Usuario", 130, True),
                                                     ("uso", "", 110, False)], "browse")
        self.arbol_cuentas.configure(height=6)
        self.arbol_cuentas.tag_configure("activa", foreground=VERDE)
        self.arbol_cuentas.bind("<Double-1>", lambda e: self.usar_cuenta_seleccionada())

        c2 = self._tarjeta(tab, "Conectar un repositorio que ya existe",
                           "Ej: https://github.com/usuario/proyecto.git (tambien GitLab o Bitbucket)")
        c2.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        self.ent_remoto = self._campo(c2.cuerpo, "URL", 0)
        boton(c2.cuerpo, "Conectar", self.guardar_remoto, ACENTO, fg="white"
              ).grid(row=0, column=2, padx=(8, 0))

        self.card_crear = self._tarjeta(tab, "Crear repositorio nuevo", "")
        self.card_crear.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(10, 8))
        cuerpo = self.card_crear.cuerpo
        self.ent_repo = self._campo(cuerpo, "Nombre", 0)
        self.ent_desc = self._campo(cuerpo, "Descripcion", 1)
        self.var_privado = tk.BooleanVar(value=False)
        self._check(cuerpo, "Repositorio privado", self.var_privado).grid(row=2, column=1, sticky="w")
        self.btn_crear = boton(cuerpo, "Crear repositorio y conectar", self.crear_repo, VERDE, fg="white")
        self.btn_crear.grid(row=3, column=1, sticky="e", pady=(10, 0))

    def _panel_registro(self, padre):
        marco = tk.Frame(padre, bg=BG)
        enc = tk.Frame(marco, bg=BG)
        enc.pack(fill="x", pady=(2, 4))
        tk.Label(enc, text="Registro de comandos", bg=BG, fg=TENUE, font=FUENTE_B).pack(side="left")
        limpiar = tk.Label(enc, text="Limpiar", bg=BG, fg=AZUL, cursor="hand2")
        limpiar.pack(side="right")
        limpiar.bind("<Button-1>", lambda e: self._vaciar(self.txt_log))
        self.txt_log = self._texto(marco, wrap="word", height=5)
        self.txt_log.tag_configure("cmd", foreground=ACENTO)
        self.txt_log.tag_configure("salida", foreground=TEXTO)
        self.txt_log.tag_configure("error", foreground=ROJO)
        self.txt_log.tag_configure("info", foreground=VERDE)
        return marco

    def _panel_vacio(self, padre):
        f = tk.Frame(padre, bg=BG)
        centro = tk.Frame(f, bg=BG)
        centro.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(centro, text="📂", font=("Segoe UI Emoji", 40), bg=BG, fg=TEXTO).pack()
        tk.Label(centro, text="Esta carpeta todavia no usa Git", bg=BG, fg=TEXTO,
                 font=("Segoe UI", 16, "bold")).pack(pady=(8, 4))
        tk.Label(centro, text="Inicializa un repositorio para empezar a guardar versiones\n"
                              "de tu proyecto y subirlo a GitHub, GitLab o Bitbucket.",
                 bg=BG, fg=TENUE, justify="center").pack()
        boton(centro, "Inicializar repositorio", self.inicializar, ACENTO, fg="white", grande=True
              ).pack(pady=(18, 8))
        boton(centro, "Elegir otra carpeta", self.elegir_proyecto).pack()
        return f

    # ----------------------------- Utilidades ------------------------- #
    def _leer_cola(self):
        try:
            while True:
                self.log(*self.cola.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._leer_cola)

    def log(self, texto, tag="salida"):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", texto + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _vaciar(self, txt):
        txt.config(state="normal")
        txt.delete("1.0", "end")
        txt.config(state="disabled")

    def aviso(self, texto, color=VERDE):
        self.lbl_estado.config(text=texto, fg=color)
        if self.id_aviso:
            self.after_cancel(self.id_aviso)
        self.id_aviso = self.after(5000, lambda: self.lbl_estado.config(text="Listo", fg=TENUE))

    def en_segundo_plano(self, trabajo, al_terminar=None, mensaje="Trabajando..."):
        """Ejecuta 'trabajo' en un hilo para que la ventana no se congele."""
        if self.ocupado:
            self.aviso("Espera a que termine la operacion actual.", AMARILLO)
            return
        self.ocupado = True
        self.config(cursor="watch")
        self.lbl_estado.config(text=mensaje, fg=TEXTO)
        self.progreso.pack(side="right")
        self.progreso.start(12)
        resultado = {}

        def hilo():
            try:
                resultado["ok"] = trabajo()
            except Exception as e:
                resultado["error"] = e

        def esperar():
            if t.is_alive():
                self.after(80, esperar)
                return
            self.ocupado = False
            self.config(cursor="")
            self.progreso.stop()
            self.progreso.pack_forget()
            self.lbl_estado.config(text="Listo", fg=TENUE)
            if "error" in resultado:
                self.log(str(resultado["error"]), "error")
                messagebox.showerror("Error", str(resultado["error"]), parent=self)
            elif al_terminar:
                al_terminar(resultado.get("ok"))
            self.refrescar()

        t = threading.Thread(target=hilo, daemon=True)
        t.start()
        self.after(80, esperar)

    def ejecutar(self, args, ok=None, error=None, mensaje="Trabajando..."):
        def fin(r):
            if r[0] == 0:
                if ok:
                    self.aviso(ok)
            else:
                messagebox.showerror(
                    "Algo salio mal",
                    error or "El comando fallo. Revisa el registro de abajo para ver el detalle.",
                    parent=self,
                )
        self.en_segundo_plano(lambda: self.git.run(*args), fin, mensaje)

    def _describir_destino(self):
        rama = self.rama_mostrada or ""
        destino = re.sub(r"\s+", "-", self.var_destino.get().strip())
        if not destino or destino == rama:
            if rama in self.remotas:
                texto, color = "Tu rama actual", TENUE
            else:
                texto, color = f"Tu rama actual (se creara en {self.plat})", TENUE
        elif destino in self.remotas:
            texto, color = f"⚠ Enviaras '{rama}' a otra rama de {self.plat}", AMARILLO
        else:
            texto, color = f"Se creara la rama '{destino}' en {self.plat}", AZUL
        self.lbl_destino.config(text=texto, fg=color)

    def _mensaje(self):
        return self.txt_msg.get("1.0", "end").strip()

    def _error_inesperado(self, tipo, valor, tb):
        self.log(f"Error inesperado: {valor}", "error")
        messagebox.showerror("Error inesperado", str(valor), parent=self)

    def _al_enfocar(self, evento):
        # Al volver a la ventana (por ejemplo desde tu editor) se actualizan los cambios
        if evento.widget is self and not self.ocupado and time.time() - self.ultimo_refresco > 1.5:
            self.refrescar()

    # ----------------------------- Proyecto --------------------------- #
    def cambiar_proyecto(self, ruta):
        self.git.ruta = os.path.abspath(ruta)
        self._verificar_confianza()
        if self.git.es_repo():
            self._excluir_programa()
        self._cargar_config()
        self.log(f"Proyecto: {self.git.ruta}", "info")
        self.refrescar()

    def _verificar_confianza(self):
        """Git bloquea carpetas de otro usuario o de discos externos ('dubious ownership')."""
        _, _, err = self.git.run("rev-parse", "--is-inside-work-tree", silencioso=True)
        if "dubious ownership" not in err:
            return
        m = re.search(r"safe\.directory '([^']+)'", err) or re.search(r"safe\.directory (\S+)", err)
        carpeta = m.group(1) if m else self.git.ruta.replace("\\", "/")
        if messagebox.askyesno(
            "Carpeta no confiable",
            "Git no confia en esta carpeta porque pertenece a otro usuario o esta en un "
            f"disco externo:\n\n{carpeta}\n\n¿Quieres marcarla como confiable?",
            parent=self,
        ):
            self.git.run("config", "--global", "--add", "safe.directory", carpeta)

    def _excluir_programa(self):
        """Evita que este programa se suba al remoto junto con tu proyecto."""
        raiz = self.git.raiz()
        if not raiz:
            return
        programa = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
        try:
            relativa = os.path.relpath(programa, raiz)
        except ValueError:  # esta en otra unidad
            return
        if relativa.startswith(".."):
            return
        regla = "/" + relativa.replace("\\", "/")
        c, o, _ = self.git.run("rev-parse", "--git-path", "info/exclude", silencioso=True)
        if c:
            return
        archivo = o.strip()
        if not os.path.isabs(archivo):
            archivo = os.path.join(self.git.ruta, archivo)
        try:
            existente = ""
            if os.path.exists(archivo):
                with open(archivo, encoding="utf-8") as f:
                    existente = f.read()
            if regla in existente.splitlines():
                return
            os.makedirs(os.path.dirname(archivo), exist_ok=True)
            with open(archivo, "a", encoding="utf-8") as f:
                f.write(("\n" if existente and not existente.endswith("\n") else "") + regla + "\n")
        except OSError:
            pass

    def _cargar_config(self):
        poner(self.ent_remoto, self.git.remoto())
        poner(self.ent_repo, os.path.basename(self.git.ruta.rstrip("\\/")).replace(" ", "-"))

    def _mostrar_repo(self, es_repo):
        if es_repo == self.modo_repo:
            return
        self.modo_repo = es_repo
        if es_repo:
            self.vacio.pack_forget()
            self.notebook.pack(fill="both", expand=True)
        else:
            self.notebook.pack_forget()
            self.vacio.pack(fill="both", expand=True)

    def _refrescar_cuentas(self, remoto):
        cuenta = self.cuenta_del_proyecto()
        # Nombre de la plataforma para los textos: la del remoto, o la de la cuenta
        clave = plataforma_de_host(host_de(remoto)) if remoto else None
        if clave:
            self.plat = PLATAFORMAS[clave]["nombre"]
        elif remoto:
            self.plat = "el servidor"
        else:
            self.plat = PLATAFORMAS[cuenta["plataforma"]]["nombre"] if cuenta else "GitHub"
        corto = self.plat if self.plat != "el servidor" else "remoto"
        self.btn_subir.config(text=f"⬆  Subir a {corto}")
        self.btn_traer.config(text=f"⬇  Traer de {corto}")
        self.btn_github.config(text=f"Ver en {corto}  ↗")

        if cuenta:
            plat = PLATAFORMAS[cuenta["plataforma"]]["nombre"]
            self.chip_cuenta.config(text=f"👤  {cuenta['apodo']} · {plat}  ▾", fg=TEXTO)
            self.card_crear.subtitulo.config(
                text=f"Se creara en {plat} con la cuenta '{cuenta['apodo']}' ({cuenta['usuario']}) "
                     "y se conectara con esta carpeta automaticamente.")
            self.btn_crear.config(text=f"Crear en {plat} y conectar")
        else:
            self.chip_cuenta.config(text="👤  Elegir cuenta  ▾", fg=AMARILLO)
            self.card_crear.subtitulo.config(
                text="Primero elige con que cuenta trabajar en este proyecto (lista de la izquierda).")
            self.btn_crear.config(text="Crear repositorio y conectar")

        seleccion = self.arbol_cuentas.selection()
        self.arbol_cuentas.delete(*self.arbol_cuentas.get_children())
        for c in self.cuentas:
            activa = cuenta is not None and c["id"] == cuenta["id"]
            self.arbol_cuentas.insert("", "end", iid=c["id"], tags=("activa",) if activa else (),
                                      values=(c["apodo"], PLATAFORMAS[c["plataforma"]]["nombre"],
                                              c["usuario"], "● en uso" if activa else ""))
        if seleccion and self.arbol_cuentas.exists(seleccion[0]):
            self.arbol_cuentas.selection_set(seleccion[0])

    def refrescar(self):
        self.ultimo_refresco = time.time()
        ruta = self.git.ruta
        nombre = os.path.basename(ruta.rstrip("\\/")) or ruta
        self.title(f"Git Manager — {nombre}")
        self.lbl_nombre.config(text=nombre)
        self.lbl_ruta.config(text=ruta)

        es_repo = self.git.es_repo()
        self._mostrar_repo(es_repo)
        if not es_repo:
            self.chip_cuenta.config(text="👤  Cuenta: —", fg=TENUE)
            self.chip_rama.config(text="⚠  Sin repositorio Git", fg=AMARILLO)
            self.chip_remoto.config(text="☁  Sin repositorio remoto", fg=TENUE)
            self.chip_cambios.config(text="—", fg=TENUE)
            self.btn_github.config(state="disabled")
            return

        rama = self.git.rama()
        remoto = self.git.remoto()
        cambios = self.git.estado()
        n = len(cambios)
        self._refrescar_cuentas(remoto)
        self.chip_rama.config(text=f"Rama: {rama or '(sin rama)'}", fg=TEXTO)
        if remoto:
            texto = re.sub(r"^https?://", "", url_web(remoto))
            if len(texto) > 48:
                texto = "…" + texto[-47:]
            self.chip_remoto.config(text="☁  " + texto, fg=TEXTO)
        else:
            self.chip_remoto.config(text="☁  Sin repositorio remoto", fg=AMARILLO)
        self.btn_github.config(state="normal" if remoto else "disabled")
        self.chip_cambios.config(
            text=f"●  {n} cambio{'s' if n != 1 else ''} sin subir" if n else "✓  Todo guardado",
            fg=AMARILLO if n else VERDE,
        )

        # Cambios
        seleccion = set(self.arbol.selection())
        self.arbol.delete(*self.arbol.get_children())
        self.estados = {}
        for xy, archivo in cambios:
            etiqueta, tag = describir(xy)
            preparado = xy[0] not in " ?"
            if preparado and xy[1] not in " ?":
                prep = "Parcial"
            else:
                prep = "✓" if preparado else ""
            self.estados[archivo] = xy
            self.arbol.insert("", "end", iid=archivo, values=(archivo, etiqueta, prep), tags=(tag,))
        self.lbl_conteo.config(text=f"({n})")
        self.notebook.tab(0, text=f"  Cambios ({n})  " if n else "  Cambios  ")
        mantener = [s for s in seleccion if self.arbol.exists(s)]
        if mantener:
            self.arbol.selection_set(mantener)
        else:
            self._previsualizar()

        # Historial
        self.arbol_log.delete(*self.arbol_log.get_children())
        for h, msg, autor, fecha in self.git.historial():
            self.arbol_log.insert("", "end", iid=h, values=(h, msg, autor, fecha))

        # Selector de destino: tu rama actual primero, luego las demas (locales y del remoto)
        remotas = self.git.ramas_remotas()
        self.remotas = set(remotas)
        opciones = [rama] if rama else []
        for r in self.git.ramas() + remotas:
            if r not in opciones:
                opciones.append(r)
        self.cmb_destino["values"] = opciones
        if rama != self.rama_mostrada:  # al cambiar de rama, el destino vuelve a ser la misma
            self.rama_mostrada = rama
            self.var_destino.set(rama or "main")
        self._describir_destino()

        # Ramas
        self.arbol_ramas.delete(*self.arbol_ramas.get_children())
        for r in self.git.ramas():
            actual = r == rama
            self.arbol_ramas.insert("", "end", iid=r, values=(r, "● actual" if actual else ""),
                                    tags=("actual",) if actual else ())

    def _previsualizar(self, _=None):
        sel = self.arbol.selection()
        if len(sel) != 1:
            self._poner_diff(f"{len(sel)} archivos seleccionados." if sel else
                             "Selecciona un archivo para ver sus cambios.\n\n"
                             "Consejo: doble clic sobre un archivo para prepararlo.")
            return
        archivo = sel[0]
        xy = self.estados.get(archivo, "  ")
        if xy == "??":
            self._poner_diff(self._leer_nuevo(archivo))
            return
        partes = []
        if xy[0] not in " ?":
            partes.append(self.git.run("diff", "--cached", "--", archivo, silencioso=True)[1])
        if xy[1] not in " ?":
            partes.append(self.git.run("diff", "--", archivo, silencioso=True)[1])
        self._poner_diff("\n".join(p for p in partes if p) or "(Sin diferencias de texto que mostrar)")

    def _leer_nuevo(self, archivo):
        ruta = os.path.join(self.git.raiz() or self.git.ruta, archivo)
        try:
            with open(ruta, "rb") as f:
                datos = f.read(300_000)
        except OSError as e:
            return f"No se pudo leer el archivo: {e}"
        if b"\0" in datos[:8000]:
            return "(Archivo binario: imagen, ejecutable, etc.)"
        lineas = datos.decode("utf-8", errors="replace").splitlines()[:3000]
        return "Archivo nuevo\n" + "\n".join("+" + l for l in lineas)

    def _poner_diff(self, texto):
        t = self.txt_diff
        t.config(state="normal")
        t.delete("1.0", "end")
        for linea in texto[:400_000].splitlines():
            if linea.startswith(("+++", "---", "diff ", "index ", "new file", "deleted file")):
                tag = "meta"
            elif linea.startswith("+"):
                tag = "add"
            elif linea.startswith("-"):
                tag = "del"
            elif linea.startswith("@@"):
                tag = "hunk"
            else:
                tag = ()
            t.insert("end", linea + "\n", tag)
        t.config(state="disabled")

    # ----------------------------- Acciones --------------------------- #
    def abrir_carpeta(self):
        if os.name == "nt":
            os.startfile(self.git.ruta)
        else:
            subprocess.Popen(["xdg-open", self.git.ruta])

    def abrir_github(self):
        remoto = self.git.remoto()
        if remoto:
            webbrowser.open(url_web(remoto))

    def elegir_proyecto(self):
        ruta = filedialog.askdirectory(initialdir=self.git.ruta, title="Elige la carpeta del proyecto")
        if ruta:
            self.cambiar_proyecto(ruta)

    def inicializar(self):
        def fin(r):
            if r[0] == 0:
                self._excluir_programa()
                self.aviso("✓ Repositorio creado. Ya puedes guardar tus cambios.")
        self.en_segundo_plano(lambda: self.git.run("init", "-b", "main"), fin, "Inicializando...")

    def _asegurar_usuario(self):
        if self.git.config("user.name") and self.git.config("user.email"):
            return True
        messagebox.showinfo("Agrega tu cuenta",
                            "Antes de guardar cambios, Git necesita saber quien eres.\n\n"
                            "Agrega la cuenta con la que vas a trabajar en este proyecto.", parent=self)
        self.agregar_cuenta(usar=True)
        return bool(self.git.config("user.name") and self.git.config("user.email"))

    def _sin_remoto(self):
        if messagebox.askyesno("Sin repositorio remoto",
                               "Esta carpeta aun no esta conectada a un repositorio en "
                               "GitHub, GitLab o Bitbucket.\n\n¿Quieres configurarlo ahora?", parent=self):
            self.notebook.select(self.tab_cuentas)

    def preparar_seleccion(self):
        rutas = list(self.arbol.selection())
        if not rutas:
            self.aviso("Selecciona uno o mas archivos primero.", AMARILLO)
            return
        self.ejecutar(["add", "--", *rutas], ok=f"✓ {len(rutas)} archivo(s) preparado(s)")

    def preparar_todos(self):
        self.ejecutar(["add", "-A"], ok="✓ Todos los archivos preparados")

    def quitar_seleccion(self):
        rutas = list(self.arbol.selection())
        if not rutas:
            self.aviso("Selecciona uno o mas archivos primero.", AMARILLO)
            return
        if self.git.tiene_commits():
            args = ["restore", "--staged", "--", *rutas]
        else:
            args = ["rm", "--cached", "-r", "-q", "--", *rutas]
        self.ejecutar(args, ok="✓ Archivos quitados de preparados")

    def descartar(self):
        rutas = list(self.arbol.selection())
        if not rutas:
            self.aviso("Selecciona uno o mas archivos primero.", AMARILLO)
            return
        if not messagebox.askyesno(
            "Descartar cambios",
            f"Se perderan los cambios de {len(rutas)} archivo(s) y los archivos nuevos se borraran.\n\n"
            "Esto NO se puede deshacer. ¿Continuar?", icon="warning", parent=self,
        ):
            return
        nuevos = [r for r in rutas if self.estados.get(r) == "??"]
        agregados = [r for r in rutas if self.estados.get(r, "  ")[0] == "A"]
        otros = [r for r in rutas if r not in nuevos and r not in agregados]

        def trabajo():
            if agregados:
                self.git.run("rm", "--cached", "-q", "--", *agregados)
            if nuevos or agregados:
                self.git.run("clean", "-f", "-q", "--", *nuevos, *agregados)
            if otros:
                self.git.run("restore", "--source=HEAD", "--staged", "--worktree", "--", *otros)
        self.en_segundo_plano(trabajo, lambda _: self.aviso("✓ Cambios descartados"), "Descartando...")

    def commit(self):
        mensaje = self._mensaje()
        if not mensaje:
            messagebox.showwarning("Falta el mensaje", "Escribe un mensaje que describa tus cambios.",
                                   parent=self)
            self.txt_msg.focus_set()
            return
        if not self._asegurar_usuario():
            return
        if not any(xy[0] not in " ?" for xy in self.estados.values()):
            if not self.estados:
                messagebox.showinfo("Sin cambios", "No hay cambios para guardar.", parent=self)
                return
            if not messagebox.askyesno("Nada preparado",
                                       "No has preparado ningun archivo.\n\n"
                                       "¿Quieres incluir todos los cambios en este commit?", parent=self):
                return
            todos = True
        else:
            todos = False

        def trabajo():
            if todos:
                self.git.run("add", "-A")
            return self.git.run("commit", "-m", mensaje)[0]

        def fin(codigo):
            if codigo == 0:
                self.txt_msg.delete("1.0", "end")
                self.aviso(f"✓ Commit guardado. Pulsa 'Subir a {self.plat}' para publicarlo.")
            else:
                messagebox.showerror("Error", "No se pudo guardar el commit. Revisa el registro.", parent=self)
        self.en_segundo_plano(trabajo, fin, "Guardando commit...")

    def subir(self):
        if not self.git.remoto():
            self._sin_remoto()
            return
        if not self._asegurar_usuario():
            return
        rama = self.git.rama() or "main"
        destino = re.sub(r"\s+", "-", self.var_destino.get().strip()) or rama
        if not self.git.nombre_rama_valido(destino):
            messagebox.showwarning("Nombre no valido",
                                   f"'{destino}' no es un nombre de rama valido.\n\n"
                                   "Usa letras, numeros, guiones o barras. Ej: diseno-nuevo", parent=self)
            return
        if destino != rama:
            existe = destino in self.remotas
            if not messagebox.askyesno(
                "Subir a otra rama",
                f"Vas a subir tu rama '{rama}' a la rama '{destino}' de {self.plat}"
                + ("." if existe else ", que todavia no existe y se creara.")
                + ("\n\nOjo: es la rama principal del proyecto." if destino in ("main", "master") else "")
                + "\n\n¿Continuar?",
                icon="warning" if existe else "question", parent=self,
            ):
                return
        mensaje = self._mensaje() or f"Actualizacion {datetime.now():%d/%m/%Y %H:%M}"

        def trabajo():
            self.git.run("add", "-A")
            if self.git.run("diff", "--cached", "--quiet", silencioso=True)[0] != 0:
                if self.git.run("commit", "-m", mensaje)[0] != 0:
                    return "commit"
            if not self.git.tiene_commits():
                return "vacio"
            if destino == rama:
                codigo, _, err = self.git.run("push", "-u", "origin", rama)
            else:  # sin -u: tu rama sigue conectada a la suya, esto es un envio puntual
                codigo, _, err = self.git.run("push", "origin", f"{rama}:{destino}")
            if codigo == 0:
                return "ok"
            if any(x in err for x in ("[rejected]", "fetch first", "non-fast-forward")):
                return "rechazado"
            return "error"

        def fin(r):
            if r == "ok":
                self.txt_msg.delete("1.0", "end")
                self.aviso(f"✓ ¡Listo! Tus cambios ya estan en {self.plat} (rama '{destino}').")
            elif r == "rechazado" and destino != rama:
                messagebox.showwarning(
                    f"{self.plat} rechazo el envio",
                    f"La rama '{destino}' en {self.plat} tiene cambios que tu rama '{rama}' no tiene.\n\n"
                    f"Para no perderlos, primero cambiate a '{destino}' (pestaña Ramas), "
                    f"trae sus cambios y fusiona '{rama}' en ella.", parent=self)
            elif r == "rechazado":
                if messagebox.askyesno(
                    f"{self.plat} tiene cambios nuevos",
                    f"En {self.plat} hay cambios que no tienes en tu computadora.\n\n"
                    f"¿Quieres traerlos ahora? Despues vuelve a pulsar 'Subir a {self.plat}'.", parent=self,
                ):
                    self.after(100, self.traer)
            elif r == "vacio":
                messagebox.showinfo("Nada que subir", "Tu proyecto no tiene archivos todavia.", parent=self)
            else:
                messagebox.showerror("No se pudo subir",
                                     "Ocurrio un problema al subir. Revisa el registro de abajo.\n\n"
                                     f"Si es la primera vez, inicia sesion en {self.plat} en la ventana que aparece "
                                     "con el usuario de la cuenta elegida.",
                                     parent=self)
        self.en_segundo_plano(trabajo, fin, f"Subiendo a {self.plat}...")

    def traer(self):
        if not self.git.remoto():
            self._sin_remoto()
            return
        if not self._asegurar_usuario():
            return
        rama = self.git.rama() or "main"

        def trabajo():
            c, o, e = self.git.run("pull", "--no-rebase", "--no-edit",
                                   "--allow-unrelated-histories", "origin", rama)
            return c, o + e

        def fin(r):
            codigo, texto = r
            if codigo == 0:
                self.aviso(f"✓ Proyecto actualizado con los cambios de {self.plat}")
            elif "CONFLICT" in texto:
                messagebox.showwarning(
                    "Conflictos",
                    "Algunos archivos se modificaron en los dos lados.\n\n"
                    "Abrelos, busca las marcas <<<<<<< y >>>>>>>, deja la version correcta "
                    "y luego guarda un commit.", parent=self)
            elif "couldn't find remote ref" in texto:
                messagebox.showinfo("Rama nueva",
                                    f"La rama '{rama}' todavia no existe en {self.plat}. Subela primero.",
                                    parent=self)
            else:
                messagebox.showerror("Error", "No se pudieron traer los cambios. Revisa el registro.",
                                     parent=self)
        self.en_segundo_plano(trabajo, fin, f"Trayendo cambios de {self.plat}...")

    def _ver_commit(self, _=None):
        sel = self.arbol_log.selection()
        if sel:
            self.en_segundo_plano(lambda: self.git.run(
                "show", "--stat", "--date=format:%d/%m/%Y %H:%M",
                "--format=%h  %s%n%an  ·  %ad", sel[0]), mensaje="Cargando commit...")

    # ----------------------------- Ramas ------------------------------ #
    def _rama_seleccionada(self):
        sel = self.arbol_ramas.selection()
        if not sel:
            self.aviso("Selecciona una rama de la lista.", AMARILLO)
            return None
        return sel[0]

    def nueva_rama(self):
        nombre = simpledialog.askstring("Nueva rama", "Nombre de la nueva rama:", parent=self)
        if nombre and nombre.strip():
            nombre = re.sub(r"\s+", "-", nombre.strip())
            self.ejecutar(["checkout", "-b", nombre], ok=f"✓ Ahora trabajas en la rama '{nombre}'")

    def cambiar_rama(self):
        rama = self._rama_seleccionada()
        if rama and rama != self.git.rama():
            self.ejecutar(["checkout", rama], ok=f"✓ Ahora trabajas en la rama '{rama}'",
                          error="No se pudo cambiar de rama.\n\n"
                                "Normalmente pasa porque tienes cambios sin guardar. "
                                "Haz un commit primero.")

    def fusionar_rama(self):
        rama = self._rama_seleccionada()
        actual = self.git.rama()
        if not rama or rama == actual:
            return
        if messagebox.askyesno("Fusionar", f"¿Traer los cambios de '{rama}' a '{actual}'?", parent=self):
            self.ejecutar(["merge", "--no-edit", rama], ok=f"✓ '{rama}' fusionada en '{actual}'",
                          error="La fusion tuvo conflictos o fallo. Revisa el registro.")

    def eliminar_rama(self):
        rama = self._rama_seleccionada()
        if not rama:
            return
        if rama == self.git.rama():
            messagebox.showinfo("Rama actual", "No puedes eliminar la rama en la que estas.", parent=self)
            return
        if not messagebox.askyesno("Eliminar rama", f"¿Eliminar la rama '{rama}'?", parent=self):
            return

        def fin(r):
            if r[0] == 0:
                self.aviso(f"✓ Rama '{rama}' eliminada")
            elif messagebox.askyesno("Cambios sin fusionar",
                                     f"La rama '{rama}' tiene cambios que no estan en otra rama.\n\n"
                                     "¿Eliminarla de todas formas? Se perderan esos cambios.",
                                     icon="warning", parent=self):
                self.after(100, lambda: self.ejecutar(["branch", "-D", rama], ok=f"✓ Rama '{rama}' eliminada"))
        self.en_segundo_plano(lambda: self.git.run("branch", "-d", rama), fin)

    # ----------------------------- Cuentas ---------------------------- #
    def cuenta_del_proyecto(self):
        """La cuenta elegida para este proyecto (se guarda en .git/config como gitmanager.cuenta)."""
        id_cuenta = self.git.config("gitmanager.cuenta")
        return next((c for c in self.cuentas if c["id"] == id_cuenta), None)

    def _menu_cuentas(self, evento=None):
        if not self.git.es_repo():
            self.aviso("Primero inicializa el repositorio.", AMARILLO)
            return
        actual = self.cuenta_del_proyecto()
        menu = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXTO, activebackground=ACENTO,
                       activeforeground="#ffffff", bd=0, font=FUENTE)
        for c in self.cuentas:
            marca = "✓  " if actual and c["id"] == actual["id"] else "     "
            menu.add_command(
                label=f"{marca}{c['apodo']}   ·   {PLATAFORMAS[c['plataforma']]['nombre']} ({c['usuario']})",
                command=lambda c=c: self.usar_cuenta(c))
        if self.cuentas:
            menu.add_separator()
        menu.add_command(label="＋  Agregar cuenta...", command=lambda: self.agregar_cuenta(usar=True))
        menu.add_command(label="⚙  Administrar cuentas",
                         command=lambda: self.notebook.select(self.tab_cuentas))
        w = self.chip_cuenta
        menu.tk_popup(w.winfo_rootx(), w.winfo_rooty() + w.winfo_height() + 2)

    def _cuenta_seleccionada(self):
        sel = self.arbol_cuentas.selection()
        cuenta = next((c for c in self.cuentas if sel and c["id"] == sel[0]), None)
        if not cuenta:
            self.aviso("Selecciona una cuenta de la lista.", AMARILLO)
        return cuenta

    def agregar_cuenta(self, usar=False):
        dialogo = DialogoCuenta(self)
        self.wait_window(dialogo)
        if not dialogo.resultado:
            return
        self.cuentas.append(dialogo.resultado)
        guardar_cuentas(self.cuentas)
        self.log(f"Cuenta agregada: {dialogo.resultado['apodo']}", "info")
        if usar or (self.git.es_repo() and not self.cuenta_del_proyecto()):
            self.usar_cuenta(dialogo.resultado, sincrono=True)
        self.refrescar()

    def editar_cuenta(self):
        cuenta = self._cuenta_seleccionada()
        if not cuenta:
            return
        dialogo = DialogoCuenta(self, cuenta)
        self.wait_window(dialogo)
        if not dialogo.resultado:
            return
        self.cuentas[self.cuentas.index(cuenta)] = dialogo.resultado
        guardar_cuentas(self.cuentas)
        if self.cuenta_del_proyecto() and self.cuenta_del_proyecto()["id"] == cuenta["id"]:
            self.usar_cuenta(dialogo.resultado, sincrono=True)  # aplica los datos nuevos
        self.aviso("✓ Cuenta actualizada")
        self.refrescar()

    def eliminar_cuenta(self):
        cuenta = self._cuenta_seleccionada()
        if not cuenta:
            return
        if not messagebox.askyesno(
            "Eliminar cuenta",
            f"¿Eliminar la cuenta '{cuenta['apodo']}' del programa?\n\n"
            "Los proyectos que la usaban conservan su autor, pero tendras que elegir otra cuenta. "
            "Tu cuenta en la plataforma no se toca.", parent=self,
        ):
            return
        self.cuentas.remove(cuenta)
        guardar_cuentas(self.cuentas)
        self.aviso(f"✓ Cuenta '{cuenta['apodo']}' eliminada")
        self.refrescar()

    def usar_cuenta_seleccionada(self):
        cuenta = self._cuenta_seleccionada()
        if cuenta:
            self.usar_cuenta(cuenta)

    def usar_cuenta(self, cuenta, sincrono=False):
        """Configura este proyecto para trabajar con la cuenta: autor de commits e inicio de sesion."""
        if not self.git.es_repo():
            self.aviso("Primero inicializa el repositorio.", AMARILLO)
            return
        servidor = servidor_de(cuenta)
        plat = PLATAFORMAS[cuenta["plataforma"]]["nombre"]
        remoto = self.git.remoto()
        if remoto and host_de(remoto) != servidor and "." in host_de(remoto):
            if not messagebox.askyesno(
                "Plataforma distinta",
                f"Este proyecto esta conectado a {host_de(remoto)}, pero la cuenta "
                f"'{cuenta['apodo']}' es de {plat} ({servidor}).\n\n"
                "Se usara para el autor de los commits, pero para subir necesitas un repositorio "
                f"de {plat}. ¿Usarla de todas formas?", parent=self,
            ):
                return

        def trabajo():
            g = self.git
            g.run("config", "--local", "user.name", cuenta["nombre"])
            g.run("config", "--local", "user.email", cuenta["email"])
            g.run("config", "--local", "gitmanager.cuenta", cuenta["id"])
            # Un solo usuario de inicio de sesion por proyecto: se borran los de cuentas anteriores
            anteriores = g.run("config", "--local", "--get-regexp", r"^credential\..*\.username$",
                               silencioso=True)[1]
            for linea in anteriores.splitlines():
                g.run("config", "--local", "--unset-all", linea.split()[0], silencioso=True)
            # Windows (Git Credential Manager) guarda una sesion por usuario; esto elige cual usar
            g.run("config", "--local", f"credential.https://{servidor}.username", cuenta["usuario"])
            # Un usuario escrito dentro de la URL tendria prioridad, asi que se quita
            if remoto:
                limpio = re.sub(r"^(https?://)[^/@]+@", r"\1", remoto)
                if limpio != remoto:
                    g.run("remote", "set-url", "origin", limpio)

        def fin(_=None):
            self.aviso(f"✓ Ahora trabajas con la cuenta '{cuenta['apodo']}' ({plat}) en este proyecto")
            self.log(f"Cuenta '{cuenta['apodo']}': la primera vez que subas, inicia sesion en {plat} "
                     f"con el usuario '{cuenta['usuario']}' en la ventana que aparecera.", "info")

        if sincrono:
            trabajo()
            fin()
        else:
            self.en_segundo_plano(trabajo, fin, "Cambiando de cuenta...")

    # ----------------------------- Repositorio ------------------------ #
    def _conectar_remoto(self, url):
        if self.git.remoto():
            return self.git.run("remote", "set-url", "origin", url)
        return self.git.run("remote", "add", "origin", url)

    def guardar_remoto(self):
        url = self.ent_remoto.get().strip()
        if not url:
            messagebox.showwarning("Falta la URL", "Pega la URL de tu repositorio.", parent=self)
            return
        cuenta = self.cuenta_del_proyecto()

        def fin(r):
            if r[0] != 0:
                return
            self.aviso(f"✓ Conectado con {host_de(url)}")
            if cuenta and host_de(url) != servidor_de(cuenta):
                messagebox.showwarning(
                    "Revisa la cuenta",
                    f"El repositorio esta en {host_de(url)}, pero la cuenta de este proyecto "
                    f"('{cuenta['apodo']}') es de {servidor_de(cuenta)}.\n\n"
                    "Elige una cuenta de esa plataforma para poder subir.", parent=self)
        self.en_segundo_plano(lambda: self._conectar_remoto(url), fin)

    def crear_repo(self):
        cuenta = self.cuenta_del_proyecto()
        if not cuenta:
            messagebox.showinfo("Elige una cuenta",
                                "Primero elige con que cuenta trabajar en este proyecto "
                                "(lista 'Tus cuentas' o el boton de cuenta de arriba).", parent=self)
            return
        nombre = self.ent_repo.get().strip().replace(" ", "-")
        if not nombre:
            messagebox.showwarning("Falta el nombre", "Escribe un nombre para el repositorio.", parent=self)
            return
        descripcion, privado = self.ent_desc.get().strip(), self.var_privado.get()
        plat = PLATAFORMAS[cuenta["plataforma"]]["nombre"]

        def trabajo():
            web, url_git = crear_repositorio(cuenta, nombre, descripcion, privado)
            self.cola.put((f"Repositorio creado: {web}", "info"))
            self._conectar_remoto(url_git)
            return web, url_git

        def fin(r):
            web, url_git = r
            poner(self.ent_remoto, url_git)
            if messagebox.askyesno("Repositorio creado",
                                   f"Se creo {web} y se conecto con esta carpeta.\n\n"
                                   "¿Quieres subir tu proyecto ahora?", parent=self):
                self.after(100, self.subir)
        self.en_segundo_plano(trabajo, fin, f"Creando repositorio en {plat}...")


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nitido en pantallas HD
        except Exception:
            pass
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True,
                       stdin=subprocess.DEVNULL, creationflags=SIN_VENTANA)
    except (OSError, subprocess.CalledProcessError):
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("Git no encontrado",
                             "Git no esta instalado o no esta en el PATH.\n\n"
                             "Descargalo de https://git-scm.com e intentalo de nuevo.")
        return
    App(carpeta_del_programa()).mainloop()


if __name__ == "__main__":
    main()
