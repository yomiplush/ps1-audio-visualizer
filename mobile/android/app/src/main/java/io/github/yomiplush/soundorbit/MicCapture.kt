package io.github.yomiplush.soundorbit

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Process
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Microphone capture + FFT spectrum for mobile SoundOrbit.
 * System audio loopback is intentionally NOT used (OS sandbox).
 */
class MicCapture {
    @Volatile private var running = false
    private var thread: Thread? = null
    private val lock = Any()
    private var snap = AudioAnalysis()

    private var beatEnv = 0f
    private var smoothBass = 0f
    private var smoothMid = 0f
    private var smoothTreble = 0f

    fun snapshot(): AudioAnalysis = synchronized(lock) { snap }

    fun start() {
        if (running) return
        running = true
        thread = Thread({ loop() }, "SoundOrbit-Mic").also {
            it.priority = Thread.MAX_PRIORITY
            it.start()
        }
    }

    fun stop() {
        running = false
        thread?.join(1500)
        thread = null
    }

    private fun loop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
        val sr = 44100
        val ch = AudioFormat.CHANNEL_IN_MONO
        val fmt = AudioFormat.ENCODING_PCM_16BIT
        val minBuf = AudioRecord.getMinBufferSize(sr, ch, fmt)
        val bufSize = max(minBuf, FFT_SIZE * 2)
        val record = try {
            AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, sr, ch, fmt, bufSize)
        } catch (_: SecurityException) {
            publishError()
            return
        }
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            publishError()
            return
        }
        val pcm = ShortArray(FFT_SIZE)
        val re = FloatArray(FFT_SIZE)
        val im = FloatArray(FFT_SIZE)
        val mag = FloatArray(FFT_SIZE / 2)
        val spectrum = FloatArray(AudioAnalysis.BANDS)
        val smooth = FloatArray(AudioAnalysis.BANDS)
        try {
            record.startRecording()
            while (running) {
                var got = 0
                while (got < FFT_SIZE && running) {
                    val n = record.read(pcm, got, FFT_SIZE - got)
                    if (n <= 0) break
                    got += n
                }
                if (got < FFT_SIZE / 2) continue
                var sumSq = 0f
                for (i in 0 until FFT_SIZE) {
                    val s = if (i < got) pcm[i] / 32768f else 0f
                    val w = 0.5f - 0.5f * cos(2.0 * PI * i / (FFT_SIZE - 1)).toFloat()
                    re[i] = s * w
                    im[i] = 0f
                    sumSq += s * s
                }
                fftInPlace(re, im)
                for (i in 0 until FFT_SIZE / 2) {
                    mag[i] = sqrt(re[i] * re[i] + im[i] * im[i])
                }
                // log-spaced bands
                val nyq = FFT_SIZE / 2
                for (b in 0 until AudioAnalysis.BANDS) {
                    val t0 = b / AudioAnalysis.BANDS.toFloat()
                    val t1 = (b + 1) / AudioAnalysis.BANDS.toFloat()
                    val i0 = max(1, (Math.pow(nyq.toDouble(), t0.toDouble())).toInt())
                    val i1 = min(nyq - 1, max(i0 + 1, (Math.pow(nyq.toDouble(), t1.toDouble())).toInt()))
                    var acc = 0f
                    for (i in i0 until i1) acc += mag[i]
                    val v = (acc / (i1 - i0)).coerceIn(0f, 20f) * 0.35f
                    smooth[b] = smooth[b] * 0.55f + v * 0.45f
                    spectrum[b] = smooth[b]
                }
                val n3 = AudioAnalysis.BANDS / 3
                var bass = 0f
                var mid = 0f
                var treble = 0f
                for (i in 0 until n3) bass += spectrum[i]
                for (i in n3 until 2 * n3) mid += spectrum[i]
                for (i in 2 * n3 until AudioAnalysis.BANDS) treble += spectrum[i]
                bass = (bass / n3).coerceIn(0f, 1.5f)
                mid = (mid / n3).coerceIn(0f, 1.5f)
                treble = (treble / max(1, AudioAnalysis.BANDS - 2 * n3)).coerceIn(0f, 1.5f)
                smoothBass = smoothBass * 0.7f + bass * 0.3f
                smoothMid = smoothMid * 0.7f + mid * 0.3f
                smoothTreble = smoothTreble * 0.7f + treble * 0.3f
                val rms = sqrt(sumSq / FFT_SIZE).coerceIn(0f, 1.5f)
                val energy = (smoothBass * 0.5f + rms * 0.7f)
                beatEnv = if (energy > beatEnv) energy else beatEnv * 0.92f
                val beat = (energy - beatEnv * 0.85f).coerceIn(0f, 1f)
                synchronized(lock) {
                    snap = AudioAnalysis(
                        spectrum = spectrum.copyOf(),
                        bass = smoothBass,
                        mid = smoothMid,
                        treble = smoothTreble,
                        rms = rms,
                        beat = beat,
                        ready = true,
                    )
                }
            }
        } catch (_: Exception) {
            publishError()
        } finally {
            try { record.stop() } catch (_: Exception) {}
            record.release()
        }
    }

    private fun publishError() {
        synchronized(lock) { snap = AudioAnalysis(ready = false) }
    }

    companion object {
        private const val FFT_SIZE = 1024

        /** In-place radix-2 FFT (real/imag). */
        fun fftInPlace(re: FloatArray, im: FloatArray) {
            val n = re.size
            var j = 0
            for (i in 1 until n) {
                var bit = n shr 1
                while (j and bit != 0) {
                    j = j xor bit
                    bit = bit shr 1
                }
                j = j xor bit
                if (i < j) {
                    val tr = re[i]; re[i] = re[j]; re[j] = tr
                    val ti = im[i]; im[i] = im[j]; im[j] = ti
                }
            }
            var len = 2
            while (len <= n) {
                val ang = (-2.0 * PI / len).toFloat()
                val wlenRe = cos(ang.toDouble()).toFloat()
                val wlenIm = sin(ang.toDouble()).toFloat()
                var i = 0
                while (i < n) {
                    var wRe = 1f
                    var wIm = 0f
                    for (k in 0 until len / 2) {
                        val uRe = re[i + k]
                        val uIm = im[i + k]
                        val vRe = re[i + k + len / 2] * wRe - im[i + k + len / 2] * wIm
                        val vIm = re[i + k + len / 2] * wIm + im[i + k + len / 2] * wRe
                        re[i + k] = uRe + vRe
                        im[i + k] = uIm + vIm
                        re[i + k + len / 2] = uRe - vRe
                        im[i + k + len / 2] = uIm - vIm
                        val nWRe = wRe * wlenRe - wIm * wlenIm
                        wIm = wRe * wlenIm + wIm * wlenRe
                        wRe = nWRe
                    }
                    i += len
                }
                len = len shl 1
            }
        }
    }
}
