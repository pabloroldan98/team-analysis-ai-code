import type { Lang } from "../types";
import { t } from "../i18n";

export default function Footer({ lang }: { lang: Lang }) {
  const url =
    lang === "es"
      ? "https://www.linkedin.com/in/pablo-roldanp/?locale=es-ES"
      : "https://www.linkedin.com/in/pablo-roldanp/";

  return (
    <footer className="border-t border-gray-200 mt-10 py-6 text-center text-xs text-gray-400">
      <p>{t(lang, "footer")}</p>
      <p className="mt-1">
        {t(lang, "created_by")}{" "}
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          Pablo Roldán
        </a>
      </p>
    </footer>
  );
}
