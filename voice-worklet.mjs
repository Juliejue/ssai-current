const TARGET_SAMPLE_RATE = 16000;
const OUTPUT_CHUNK_SAMPLES = 3200; // Tencent's recommended 200 ms / 6400-byte PCM packet.

function toPcm16(sample) {
  const clamped = Math.max(-1, Math.min(1, sample));
  return clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
}

/**
 * Streaming resampler whose fractional position survives AudioWorklet's
 * 128-frame process boundaries. Resampling each block independently produces
 * the wrong effective sample rate at both 44.1 kHz and 48 kHz.
 */
export class Pcm16Resampler {
  constructor(inputSampleRate, targetSampleRate = TARGET_SAMPLE_RATE, chunkSamples = OUTPUT_CHUNK_SAMPLES) {
    if (!(inputSampleRate > 0) || !(targetSampleRate > 0) || !(chunkSamples > 0)) {
      throw new TypeError('sample rates and chunk size must be positive');
    }
    this.ratio = inputSampleRate / targetSampleRate;
    this.chunkSamples = chunkSamples;
    this.tail = new Float32Array(0);
    this.position = 0;
    this.output = new Int16Array(chunkSamples);
    this.outputLength = 0;
  }

  push(channel) {
    if (!channel || channel.length === 0) return [];

    const input = new Float32Array(this.tail.length + channel.length);
    input.set(this.tail, 0);
    input.set(channel, this.tail.length);
    const chunks = [];

    while (this.position + 1 < input.length) {
      const left = Math.floor(this.position);
      const fraction = this.position - left;
      const sample = input[left] + (input[left + 1] - input[left]) * fraction;
      this.output[this.outputLength++] = toPcm16(sample);

      if (this.outputLength === this.chunkSamples) {
        chunks.push(this.output);
        this.output = new Int16Array(this.chunkSamples);
        this.outputLength = 0;
      }
      this.position += this.ratio;
    }

    const consumed = Math.min(Math.floor(this.position), input.length);
    this.tail = input.slice(consumed);
    this.position -= consumed;
    return chunks;
  }

  flush() {
    if (!this.outputLength) return null;
    const finalChunk = this.output.slice(0, this.outputLength);
    this.output = new Int16Array(this.chunkSamples);
    this.outputLength = 0;
    return finalChunk;
  }
}

if (typeof AudioWorkletProcessor !== 'undefined' && typeof registerProcessor === 'function') {
  class CurrentPcmProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
      this.resampler = new Pcm16Resampler(sampleRate);
      this.port.onmessage = event => {
        if (!event.data || event.data.type !== 'flush') return;
        const finalChunk = this.resampler.flush();
        if (finalChunk) this.send(finalChunk);
        this.port.postMessage({ type: 'flushed' });
      };
    }

    send(chunk) {
      this.port.postMessage({ type: 'audio', buffer: chunk.buffer }, [chunk.buffer]);
    }

    process(inputs) {
      const channel = inputs[0] && inputs[0][0];
      if (!channel) return true;
      for (const chunk of this.resampler.push(channel)) this.send(chunk);
      return true;
    }
  }

  registerProcessor('current-pcm', CurrentPcmProcessor);
}
