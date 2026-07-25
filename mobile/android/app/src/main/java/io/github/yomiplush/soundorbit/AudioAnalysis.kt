package io.github.yomiplush.soundorbit

/** Thread-safe snapshot of mic analysis. */
data class AudioAnalysis(
    val spectrum: FloatArray = FloatArray(BANDS),
    val bass: Float = 0f,
    val mid: Float = 0f,
    val treble: Float = 0f,
    val rms: Float = 0f,
    val beat: Float = 0f,
    val ready: Boolean = false,
) {
    companion object {
        const val BANDS = 48
    }
}
