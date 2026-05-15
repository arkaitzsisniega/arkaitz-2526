"use client";

/**
 * AuthGate — barrera de acceso simple para el crono.
 *
 * Pide una contraseña al primer acceso. Si es correcta, guarda en
 * localStorage `inter_crono_auth=1` y deja pasar para futuras visitas.
 *
 * Seguridad: la contraseña NO se almacena en plano en el bundle.
 * Se guarda solo su hash SHA-256. Al validar, hashea el input y
 * compara. Esto evita que la contraseña aparezca literal en el JS
 * público (cualquiera con DevTools la vería).
 *
 * NOTA: esto es protección BÁSICA (anti-curioso). No es seguridad
 * criptográfica real: cualquier técnico con dev tools puede
 * setear `localStorage.inter_crono_auth = "1"` y entrar. Para más
 * seguridad habría que server-side auth, pero como es una PWA
 * estática y los datos NO son sensibles, esto es suficiente.
 */
import { useEffect, useState } from "react";

// SHA-256 de la contraseña actual. Calculado con:
//   echo -n "inter1977" | shasum -a 256
const PASS_HASH = "2198c9c222da8099db935f222ae09b1b74ffc1d0ccdbfcc830456ab0c07a013d";
const STORAGE_KEY = "inter_crono_auth";

async function sha256(text: string): Promise<string> {
  const buf = new TextEncoder().encode(text);
  const hashBuf = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hashBuf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  // Estado: undefined = aún no comprobado (SSR / primer render), true = ok, false = pedir pass
  const [autorizado, setAutorizado] = useState<boolean | undefined>(undefined);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [comprobando, setComprobando] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY) === "1") {
        setAutorizado(true);
      } else {
        setAutorizado(false);
      }
    } catch {
      // Si localStorage no funciona (modo privado, etc.), pedir pass cada vez
      setAutorizado(false);
    }
  }, []);

  const intentarEntrar = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || comprobando) return;
    setComprobando(true);
    setError("");
    try {
      const hash = await sha256(input.trim());
      if (hash === PASS_HASH) {
        try {
          localStorage.setItem(STORAGE_KEY, "1");
        } catch {
          // si falla, al menos dejar entrar esta sesión
        }
        setAutorizado(true);
      } else {
        setError("Contraseña incorrecta.");
        setInput("");
      }
    } catch (e: any) {
      setError(`Error al validar: ${e?.message || e}`);
    } finally {
      setComprobando(false);
    }
  };

  // Mientras comprobamos por primera vez, no renderizar nada (evita flash de
  // login antes de que veamos que estaba autorizado).
  if (autorizado === undefined) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <span className="text-sm text-zinc-500">Cargando…</span>
      </div>
    );
  }

  if (autorizado) {
    return <>{children}</>;
  }

  // Pantalla de login
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center p-6">
      <div className="bg-zinc-900 rounded-2xl p-8 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">🔐</div>
          <h1 className="text-2xl font-bold">Crono Inter FS</h1>
          <p className="text-sm text-zinc-400 mt-2">
            Acceso restringido al cuerpo técnico. Introduce la contraseña.
          </p>
        </div>
        <form onSubmit={intentarEntrar}>
          <input type="password"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Contraseña"
            autoComplete="current-password"
            autoFocus
            className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-4 py-3 text-lg text-center focus:outline-none focus:border-emerald-600" />
          {error && (
            <div className="text-red-400 text-sm text-center mt-3">{error}</div>
          )}
          <button type="submit" disabled={!input.trim() || comprobando}
            className={`w-full mt-4 py-3 rounded-lg text-lg font-bold ${
              !input.trim() || comprobando
                ? "bg-zinc-700 opacity-60"
                : "bg-emerald-700 hover:bg-emerald-600"
            }`}>
            {comprobando ? "Comprobando…" : "Entrar"}
          </button>
        </form>
        <p className="text-xs text-zinc-600 text-center mt-6">
          Si la has olvidado, pregunta a Arkaitz.
        </p>
      </div>
    </div>
  );
}
