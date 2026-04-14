import { Composition } from "remotion";
import { SubtitleVideo } from "./SubtitleVideo";

// Duration based on the transcript (2035.96 - 1101.12 = 934.84 seconds)
// At 30 fps: 934.84 * 30 = 28045 frames
const DURATION_IN_FRAMES = 28045;
const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="SubtitleVideo"
      component={SubtitleVideo}
      durationInFrames={DURATION_IN_FRAMES}
      fps={FPS}
      width={1080}
      height={1920}
    />
  );
};
