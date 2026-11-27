/** A plain GET form: works without JavaScript; /v turns `?code=` into /v/<code>. */
export function CodeForm({ title = "Проверить сертификат", defaultValue = "" }: { title?: string; defaultValue?: string }) {
  return (
    <form action="/v" className="rounded-2xl bg-content1 p-5 shadow-[var(--lift)] sm:p-6" method="get">
      <label className="block text-base font-semibold" htmlFor="code">
        {title}
      </label>
      <p className="mt-1 text-sm text-default-500">Введите код с сертификата — он напечатан под QR-кодом.</p>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        <input
          autoCapitalize="characters"
          autoComplete="off"
          className="h-11 w-full min-w-0 rounded-xl border border-default-200 bg-background px-3 font-mono text-base uppercase tracking-wider outline-none placeholder:normal-case placeholder:tracking-normal placeholder:text-default-400 focus:border-primary focus:ring-2 focus:ring-primary/30"
          defaultValue={defaultValue}
          id="code"
          inputMode="text"
          maxLength={20}
          name="code"
          placeholder="XXXX-XXXX-XXXX"
          required
          spellCheck={false}
        />
        <button
          className="h-11 shrink-0 rounded-xl bg-[#007eae] px-5 text-sm font-semibold text-white hover:bg-[#006b94] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#00a0dc]"
          type="submit"
        >
          Проверить
        </button>
      </div>
    </form>
  );
}
