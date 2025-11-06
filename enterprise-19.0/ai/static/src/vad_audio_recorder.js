import { rpc } from "@web/core/network/rpc";
import { url } from "@web/core/utils/urls";

/**
 * @typedef {object} RealTimeSessionInfo
 * @property {object} client_secret
 * @property {string} client_secret.value The client secret value for WebSocket authentication.
 * @property {string} [expires_at] The expiration timestamp of the session.
 * @property {string} [session_id] The ID of the real-time session.
 */

export default class VADAudioRecorder {
    static instance = null;

    /**
     * @type {WebSocket}
     */
    static socket = null;
    /**
     * @type {AudioContext}
     */
    static audioContext = null;

    /**
     * @type {MediaStream}
     */
    static audioStream = null;

    static listenerCount = 0;

    constructor(
        onMessage,
        filterOptions = {
            type: "bandpass",
            frequency: 1850,
            Q: 4.0,
        },
        checkIntervalMs = 100,
        silenceThreshold = 0.01,
        silenceDurationMs = 500
    ) {
        this.onMessage = onMessage;
        this.filterOptions = filterOptions;
        this.state = "inactive";

        this.checkIntervalMs = checkIntervalMs;
        this.silenceThreshold = silenceThreshold;
        this.silenceDurationMs = silenceDurationMs;
    }

    /**
     * This method will start the recording of the audio and the realtime transcription session.
     * @param {string} language the language to use for the transcription session
     * @param {string} prompt the prompt to give to the transcription tool
     */
    async startRecording(language, prompt) {
        /** @type{RealTimeSessionInfo} */
        const sessionInfo = await rpc("/ai/transcription/session", {
            language,
            prompt,
        });
        if (VADAudioRecorder.audioStream === null) {
            VADAudioRecorder.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    noiseSuppression: true,
                    echoCancellation: true,
                },
            });
        }

        await this.setupTranscriptionSession(sessionInfo);
        VADAudioRecorder.listenerCount++;
        this.state = "recording";
    }

    /**
     * This method sets up the transcription session. This includes setting up the audio pipeline
     * to filter the audio and formatting it with the help of the PCM16AudioProcessor. The method
     * also starts the {@link WebSocket} session with OpenAI.
     * @param {RealTimeSessionInfo} sessionInfo the information about the session containing the ephemeral token
     */
    async setupTranscriptionSession(sessionInfo) {
        if (!VADAudioRecorder.socket) {
            VADAudioRecorder.socket = new WebSocket(
                "wss://api.openai.com/v1/realtime?intent=transcription",
                [
                    "realtime",
                    // Auth
                    "openai-insecure-api-key." + sessionInfo.client_secret.value,
                    "openai-beta.realtime-v1",
                ]
            );
        }
        this.socketMessageListener = (event) => {
            const jsonData = JSON.parse(event.data);
            this.onMessage(jsonData);
        };
        VADAudioRecorder.socket.addEventListener("message", this.socketMessageListener);

        VADAudioRecorder.socket.onerror = (error) => {
            this.state = "stopped";
            console.error(error);
        };

        if (!VADAudioRecorder.audioContext || VADAudioRecorder.audioContext.state === "closed") {
            VADAudioRecorder.audioContext = new AudioContext();
            const audioContext = VADAudioRecorder.audioContext;

            const sourceNode = audioContext.createMediaStreamSource(VADAudioRecorder.audioStream);
            const filterNode = audioContext.createBiquadFilter();
            filterNode.type = this.filterOptions.type;
            filterNode.frequency.setValueAtTime(
                this.filterOptions.frequency,
                audioContext.currentTime
            );
            filterNode.Q.setValueAtTime(this.filterOptions.Q, audioContext.currentTime);

            const analyzerNode = audioContext.createAnalyser();

            const workletUrl = url("/ai/static/src/worklets/pcm16_audio_processor.js");
            await audioContext.audioWorklet.addModule(workletUrl);
            const pcm16AudioProcessorNode = new AudioWorkletNode(audioContext, "pcm16-processor");

            if (audioContext.state === "suspended") {
                await audioContext.resume();
            }
            sourceNode.connect(filterNode);
            filterNode.connect(analyzerNode);
            analyzerNode.connect(pcm16AudioProcessorNode);
            pcm16AudioProcessorNode.connect(audioContext.destination);

            const detectVoiceActivity = () => {
                const dataArray = new Uint8Array(analyzerNode.frequencyBinCount);
                analyzerNode.getByteFrequencyData(dataArray);

                const normalizedTotalDb = dataArray.reduce(
                    (sum, dbValue) => sum + dbValue / 255,
                    0
                );

                const avgDb = normalizedTotalDb / analyzerNode.frequencyBinCount;

                if (avgDb > this.silenceThreshold) {
                    if (this.silenceTimer !== null) {
                        clearTimeout(this.silenceTimer);
                        this.silenceTimer = null;
                    }
                } else {
                    const socket = VADAudioRecorder.socket;
                    if (this.silenceTimer === null && socket !== null && socket.readyState === 1) {
                        this.silenceTimer = setTimeout(() => {
                            socket.send(
                                JSON.stringify({
                                    type: "input_audio_buffer.commit",
                                })
                            );
                        }, this.silenceDurationMs);
                    }
                }
            };

            this.detectionInterval = setInterval(detectVoiceActivity, this.checkIntervalMs);

            pcm16AudioProcessorNode.port.onmessage = (event) => {
                const socket = VADAudioRecorder.socket;
                if (socket !== null && socket.readyState === 1) {
                    socket.send(
                        JSON.stringify({
                            type: "input_audio_buffer.append",
                            audio: btoa(String.fromCharCode(...new Uint8Array(event.data))),
                        })
                    );
                }
            };
        }
    }

    /**
     * This method stops the recording of the audio. Specifically, closing the socket, and
     * disposing all the media resources currently in use.
     */
    stopRecording() {
        VADAudioRecorder.listenerCount = Math.max(VADAudioRecorder.listenerCount - 1, 0);
        VADAudioRecorder.socket?.removeEventListener("message", this.socketMessageListener);

        if (VADAudioRecorder.listenerCount === 0) {
            clearTimeout(this.silenceTimer);
            clearInterval(this.detectionInterval);
            VADAudioRecorder.audioContext?.close();
            VADAudioRecorder.socket?.close();
            VADAudioRecorder.audioStream?.getTracks().forEach((track) => track.stop());

            VADAudioRecorder.socket = null;
            VADAudioRecorder.audioContext = null;
            VADAudioRecorder.audioStream = null;
            this.state = "stopped";
        }
    }
}
