// The "Payment Outcomes" ring chart. Each slice is a circle outline drawn only part-way round
// (stroke-dasharray), rotated to start where the previous slice ended.

const R = 70;
const CIRCUMFERENCE = 2 * Math.PI * R;
const GAP = 3; // white gap between slices, in px along the ring

export default function Donut({ slices, centerValue, centerLabel }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  let offset = 0;

  return (
    <div className="donut">
      <svg viewBox="0 0 180 180" role="img"
           aria-label={slices.map((s) => `${s.label}: ${s.value}`).join(", ")}>
        <circle cx="90" cy="90" r={R} fill="none" stroke="var(--track)" strokeWidth="22" />
        {total > 0 && slices.map((s) => {
          const length = (s.value / total) * CIRCUMFERENCE;
          const visible = Math.max(length - (slices.filter((x) => x.value).length > 1 ? GAP : 0), 0);
          const el = (
            <circle key={s.label} cx="90" cy="90" r={R} fill="none" stroke={s.color} strokeWidth="22"
                    strokeDasharray={`${visible} ${CIRCUMFERENCE - visible}`}
                    strokeDashoffset={-offset} transform="rotate(-90 90 90)" />
          );
          offset += length;
          return el;
        })}
      </svg>
      <div className="donut-center">
        <strong>{centerValue}</strong>
        <span>{centerLabel}</span>
      </div>
    </div>
  );
}
