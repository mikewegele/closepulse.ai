import React, {useEffect, useRef} from 'react';

const PiPCircleWithTexts = () => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext('2d');
        if (!ctx || !canvas) return;

        let animationFrameId: number;

        const draw = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            ctx.fillStyle = 'red';
            ctx.beginPath();
            ctx.arc(75, 75, 50, 0, 2 * Math.PI);
            ctx.fill();

            ctx.fillStyle = 'black';
            ctx.font = '16px Arial';
            const texts = ['Sales Vorschlag 1', 'Sales Vorschlag 2', 'Sales Vorschlag 3'];
            texts.forEach((text, i) => {
                ctx.fillText(text, 10, 150 + i * 25);
            });

            animationFrameId = requestAnimationFrame(draw);
        };

        draw();

        return () => cancelAnimationFrame(animationFrameId);
    }, []);

    const startPiP = async () => {
        if (!videoRef.current || !canvasRef.current) return;

        if (!videoRef.current.srcObject) {
            videoRef.current.srcObject = canvasRef.current.captureStream(30);
            await videoRef.current.play();
        }

        try {
            if (document.pictureInPictureEnabled && !document.pictureInPictureElement) {
                await videoRef.current.requestPictureInPicture();
            }
        } catch (error) {
            console.error('Picture-in-Picture Fehler:', error);
        }
    };

    return (
        <>
            <canvas ref={canvasRef} width={200} height={250} style={{display: 'none'}}/>
            <video ref={videoRef} style={{display: 'none'}} muted/>
            <button onClick={startPiP}>Picture-in-Picture starten</button>
        </>
    );
};

export default PiPCircleWithTexts;
