const test = require('node:test');
const assert = require('node:assert/strict');

const resamplerModule = import('../voice-worklet.mjs');

async function resampleOneSecond(inputSampleRate) {
  const { Pcm16Resampler } = await resamplerModule;
  const resampler = new Pcm16Resampler(inputSampleRate);
  const chunks = [];

  for (let offset = 0; offset < inputSampleRate; offset += 128) {
    const length = Math.min(128, inputSampleRate - offset);
    const block = new Float32Array(length);
    for (let index = 0; index < length; index++) {
      block[index] = Math.sin(2 * Math.PI * 440 * (offset + index) / inputSampleRate);
    }
    chunks.push(...resampler.push(block));
  }

  const finalChunk = resampler.flush();
  if (finalChunk) chunks.push(finalChunk);
  return chunks;
}

for (const inputSampleRate of [44100, 48000]) {
  test(`continuous resampling keeps one second at 16 kHz from ${inputSampleRate} Hz`, async () => {
    const chunks = await resampleOneSecond(inputSampleRate);
    const sampleCount = chunks.reduce((total, chunk) => total + chunk.length, 0);

    assert.ok(Math.abs(sampleCount - 16000) <= 1, `got ${sampleCount} samples`);
    assert.ok(chunks.slice(0, -1).every(chunk => chunk.length === 3200));
    assert.ok(chunks.at(-1).length <= 3200);
  });
}

test('PCM conversion clamps samples instead of wrapping them', async () => {
  const { Pcm16Resampler } = await resamplerModule;
  const resampler = new Pcm16Resampler(16000, 16000, 2);
  const chunks = resampler.push(Float32Array.from([-2, 2, 0]));

  assert.equal(chunks.length, 1);
  assert.deepEqual(Array.from(chunks[0]), [-32768, 32767]);
});
