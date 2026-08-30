import { NoObservation } from "@/components/instrument/NoObservation";
import { Panel } from "@/components/instrument/Panel";
import { TechnologyRow } from "@/components/trends/TechnologyRow";
import type { TechnologyCard, Vocabulary } from "@/lib/types";

type Props = {
  title: string;
  caption: string;
  items: readonly TechnologyCard[];
  vocabulary: Vocabulary | null;
  emptyReason?: string | null;
};

/**
 * One ranked band of the radar: heating, cooling, emerging or anomalous.
 *
 * Each band states its own definition in the header. "Heating" is not a mood —
 * it is star velocity above this technology's own 28-day baseline — and a
 * technology intelligence system has to say which.
 */
export function SignalBand({ title, caption, items, vocabulary, emptyReason }: Props) {
  return (
    <Panel
      title={title}
      caption={caption}
      right={
        <span className="font-mono text-[10px] tabular-nums text-faint">
          {items.length ? `${items.length}` : "—"}
        </span>
      }
    >
      {items.length ? (
        <ol>
          {items.map((card, index) => (
            <li key={card.slug}>
              <TechnologyRow card={card} vocabulary={vocabulary} index={index} />
            </li>
          ))}
        </ol>
      ) : (
        <NoObservation
          title="No signal in this band"
          reason={emptyReason ?? undefined}
          className="py-10"
        />
      )}
    </Panel>
  );
}
