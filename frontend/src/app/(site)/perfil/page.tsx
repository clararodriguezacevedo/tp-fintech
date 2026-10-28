import { setProfileAction } from "@/app/(site)/actions";
import { ApiFailure, attempt, PageTitle } from "@/components/ui";
import { api, type ProfileName } from "@/lib/api/client";

export const metadata = { title: "Perfil de inversor | El Parqué" };

const PROFILES: { key: ProfileName; name: string; text: string }[] = [
  { key: "conservador", name: "Conservador", text: "Priorizás no perder. Solo bonos y otros activos de riesgo bajo." },
  { key: "moderado", name: "Moderado", text: "Aceptás algo de riesgo. Suma acciones, CEDEARs y ETFs que se mueven poco, y bonos más volátiles." },
  { key: "arriesgado", name: "Arriesgado", text: "Aceptás pérdidas grandes buscando más ganancia. Incluye las acciones y CEDEARs más volátiles." },
];

const pct = (x: number) => `${(x * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })}%`;

export default async function ProfilePage() {
  const [profile, model] = await Promise.all([attempt(api.profile), attempt(api.model)]);
  if (!profile.ok) return <ApiFailure error={profile.error} />;
  const p = profile.data;
  const fromIol = p.source === "iol";

  return (
    <div className="max-w-2xl">
      <PageTitle>Perfil de inversor</PageTitle>
      <p className="text-text-2">
        Por las reglas de la CNV, solo te recomendamos activos que van con tu perfil. Todo lo que se mueve más que eso
        aparece como &quot;fuera de tu perfil&quot;: no se recomienda comprarlo, y para comprarlo igual tenés que confirmarlo.
      </p>
      <p className="mt-4">
        Tu perfil: <strong className="capitalize">{p.profile}</strong>
        <span className="text-text-2">
          {fromIol ? ", según tu test del inversor en IOL." : p.source === "declared" ? ", el que elegiste acá." : ", por defecto hasta que elijas uno."}
        </span>
      </p>
      {!fromIol && p.iol_test_pending && (
        <p className="mt-2 text-sm text-text-3">
          IOL todavía no tiene tu perfil: te pide hacer o actualizar el test del inversor. Cuando lo hagas, se usa el de IOL.
        </p>
      )}

      <form action={setProfileAction} className="mt-8 space-y-3">
        {PROFILES.map((o) => {
          const current = o.key === p.profile;
          const m = model.ok ? model.data : null;
          return (
            <button
              key={o.key}
              name="profile"
              value={o.key}
              disabled={fromIol || current}
              className={`block w-full rounded-xl border p-4 text-left disabled:cursor-default ${current ? "border-text" : "border-border hover:border-text"}`}
            >
              <span className="flex items-baseline justify-between gap-4">
                <span className="font-semibold">{o.name}</span>
                {current && <span className="text-sm text-text-2">Tu perfil</span>}
              </span>
              <span className="mt-1 block text-text-2">{o.text}</span>
              {m && (
                <span className="mt-2 block text-sm text-text-3">
                  Hasta riesgo {["", "bajo", "medio", "alto"][m.profile_max_level[o.key]]}. Por compra arriesga hasta el {pct(m.profile_risk_per_trade[o.key])} de la cartera
                  si toca el stop loss, y ningún activo pasa el {pct(m.profile_max_position[o.key])}.
                </span>
              )}
            </button>
          );
        })}
      </form>
      {fromIol && <p className="mt-3 text-sm text-text-3">Para cambiarlo, hacé de nuevo el test del inversor en IOL.</p>}

      {model.ok && (
        <section className="mt-10">
          <h2 className="mb-3 text-lg font-semibold">Cómo se mide el riesgo de cada activo</h2>
          <ul className="list-disc space-y-1 pl-5 text-text-2">
            <li><strong className="text-text">Bajo:</strong> bonos y obligaciones negociables que se mueven hasta {pct(model.data.bond_low_vol)} al año.</li>
            <li><strong className="text-text">Medio:</strong> el resto de los bonos, y acciones, CEDEARs y ETFs que se mueven hasta {pct(model.data.equity_mid_vol)} al año.</li>
            <li><strong className="text-text">Alto:</strong> acciones, CEDEARs y ETFs que se mueven más, y cualquier activo sin historial suficiente.</li>
          </ul>
          <p className="mt-2 text-sm text-text-3">El movimiento se mide con los precios de los últimos 3 meses y se actualiza cada día.</p>
        </section>
      )}
    </div>
  );
}
