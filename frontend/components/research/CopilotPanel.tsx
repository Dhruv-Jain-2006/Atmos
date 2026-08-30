type Props = {
  technologyName: string;
};

/**
 * The Research Copilot's seat, held open and honestly empty.
 *
 * The research engine is explicitly out of scope for this slice, so this does not
 * fetch, stream or fake an answer. It shows the questions the Copilot is being
 * built to answer against Internet Weather's own data, and it is disabled rather
 * than absent so the page's information architecture is the real one.
 *
 * A composer that accepted input and returned a canned reply would be the exact
 * failure mode CLAUDE.md names: an LLM wrapper wearing an observatory's clothes.
 */
export function CopilotPanel({ technologyName }: Props) {
  const questions = [
    `Is ${technologyName}'s growth driven by a few repositories?`,
    "What changed in the last 7 days, and what was the trigger?",
    "How does this compare with its subdomain's baseline?",
    "What evidence contradicts the current weather state?",
  ];

  return (
    <div className="px-4 py-4">
      <p className="max-w-2xl text-[11.5px] leading-relaxed text-faint">
        The Copilot answers questions by querying this platform&apos;s structured signals and
        citing the evidence it used — it is not a general chatbot. It is not implemented in this
        slice; the contract exists (<span className="font-mono text-[10.5px] text-dim">POST
        /api/research</span>, <span className="font-mono text-[10.5px] text-dim">POST
        /api/research/&#123;id&#125;/chat</span>) and both routes currently return{" "}
        <span className="font-mono text-[10.5px] text-dim">501 Not Implemented</span>.
      </p>

      <ul className="mt-3.5 flex flex-wrap gap-2">
        {questions.map((question) => (
          <li
            key={question}
            className="rounded-sm border border-edge bg-grid/40 px-2.5 py-1.5 text-[11px] text-ghost"
          >
            {question}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-center gap-2 rounded-sm border border-edge bg-deep/60 px-3 py-2.5">
        <input
          disabled
          aria-label="Ask the Research Copilot (not yet available)"
          placeholder="Ask about this technology…"
          className="min-w-0 flex-1 cursor-not-allowed bg-transparent font-mono text-[11px] text-ghost placeholder:text-ghost focus:outline-none"
        />
        <span className="rounded-sm border border-edge px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
          not available
        </span>
      </div>
    </div>
  );
}
