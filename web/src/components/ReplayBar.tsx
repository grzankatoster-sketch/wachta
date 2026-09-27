interface Props {
  active: boolean;
  onToggle: () => void;
  currentTime: number;
  max: number;
  setCurrentTime: (t: number) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  startEpoch: number | null;
}

export function ReplayBar({ active, onToggle, currentTime, max, setCurrentTime, playing, setPlaying, startEpoch }: Props) {
  const clock = startEpoch ? new Date((startEpoch + currentTime) * 1000).toLocaleTimeString("pl-PL") : "";
  return (
    <div className="replay">
      <button onClick={onToggle}>{active ? "Wróć na żywo" : "Odtwórz ostatnie 6 h"}</button>
      {active && (
        <>
          <button onClick={() => setPlaying(!playing)}>{playing ? "Pauza" : "Start"}</button>
          <input type="range" min={0} max={max} value={currentTime} onChange={(e) => setCurrentTime(Number(e.target.value))} />
          <span>{clock}</span>
        </>
      )}
    </div>
  );
}
