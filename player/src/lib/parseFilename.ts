export interface ParsedFilename {
  date: string;
  startTime: string;
  endTime: string;
  personTag: string;
}

export function parseFilename(filename: string): ParsedFilename | null {
  // Format: [日期]_[开始时间]_[结束时间]_[人物标签].mp3
  // Example: 2025年2月14日_001201_002424_25岁C9硕士物理女生.mp3
  const match = filename.match(
    /^(.+?)_(\d{6})_(\d{6})_(.+)\.mp3$/
  );

  if (!match) return null;

  const [, date, startTime, endTime, personTag] = match;

  // Format time: 001201 -> 00:12:01
  const formatTime = (t: string) =>
    `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}`;

  return {
    date,
    startTime: formatTime(startTime),
    endTime: formatTime(endTime),
    personTag,
  };
}
