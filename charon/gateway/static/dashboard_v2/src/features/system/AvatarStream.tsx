/**
 * @file src/features/system/AvatarStream.tsx
 * @description
 */
import React, { useEffect, useRef, useState } from 'react';
import { wsClient, CharonWSFrame } from '../../core/ws/CharonStream';

export const AvatarStream: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [emotion, setEmotion] = useState<string>('attentive');
  const [speechText, setSpeechText] = useState<string>('');
  const [pointerTarget, setPointerTarget] = useState<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const unsubStream = wsClient.subscribe('proactive_interjection', (frame: CharonWSFrame) => {
      if (frame.payload?.text) setSpeechText(frame.payload.text);
      if (frame.payload?.avatar_state?.emotion) setEmotion(frame.payload.avatar_state.emotion);
      if (frame.payload?.hud_overlay?.pointer_target) {
        setPointerTarget(frame.payload.hud_overlay.pointer_target);
      }
    });

    const unsubMotion = wsClient.subscribe('cursor_motion', (frame: CharonWSFrame) => {
      if (frame.data?.x !== undefined && frame.data?.y !== undefined) {
        setPointerTarget({ x: frame.data.x, y: frame.data.y });
      }
    });

    return () => {
      unsubStream();
      unsubMotion();
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    let phase = 0;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      phase += 0.05;

      // Render Animated HUD Orb/Avatar Viseme
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const radius = 40 + Math.sin(phase) * 4;

      const gradient = ctx.createRadialGradient(centerX, centerY, 5, centerX, centerY, radius);
      gradient.addColorStop(0, emotion === 'speaking' ? '#60A5FA' : '#34D399');
      gradient.addColorStop(1, 'transparent');

      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Render Pointer Target Indicator
      if (pointerTarget) {
        ctx.strokeStyle = 'rgba(239, 68, 68, 0.7)';
        ctx.lineWidth = 2;
        ctx.strokeRect(pointerTarget.x - 10, pointerTarget.y - 10, 20, 20);
      }

      animationId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animationId);
  }, [emotion, pointerTarget]);

  return (
    <div className="relative p-4 bg-slate-900 rounded-xl border border-slate-800 text-white">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
          Concierge Stream • {emotion}
        </span>
        {pointerTarget && (
          <span className="text-xs text-emerald-400">
            Target: ({pointerTarget.x.toFixed(0)}, {pointerTarget.y.toFixed(0)})
          </span>
        )}
      </div>
      <canvas ref={canvasRef} width={320} height={180} className="w-full h-44 bg-slate-950 rounded-lg" />
      {speechText && (
        <p className="mt-3 text-sm text-slate-200 bg-slate-800/80 p-2.5 rounded border border-slate-700">
          "{speechText}"
        </p>
      )}
    </div>
  );
};