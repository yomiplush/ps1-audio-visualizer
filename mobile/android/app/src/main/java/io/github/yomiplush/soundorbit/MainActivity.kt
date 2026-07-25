package io.github.yomiplush.soundorbit

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * SoundOrbit Mobile — mic-driven PS1 CRT visualizer (OpenGL ES 3).
 * Sideload APK; grant RECORD_AUDIO for reaction to ambient sound.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var glView: GLSurfaceView
    private lateinit var mic: MicCapture
    private var renderer: VisualizerRenderer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemUi()

        mic = MicCapture()
        glView = GLSurfaceView(this).apply {
            setEGLContextClientVersion(3)
            // Prefer discrete-ish: no MSAA
            setEGLConfigChooser(8, 8, 8, 8, 16, 0)
            preserveEGLContextOnPause = true
        }
        setContentView(glView)

        if (hasMicPermission()) {
            startVisualizer()
        } else {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.RECORD_AUDIO),
                REQ_MIC,
            )
            Toast.makeText(this, "マイク権限が必要です（システム音声ではなく周囲の音）", Toast.LENGTH_LONG).show()
        }
    }

    private fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    private fun startVisualizer() {
        if (renderer != null) return
        mic.start()
        val r = VisualizerRenderer(this, mic)
        renderer = r
        glView.setRenderer(r)
        glView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_MIC && grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        ) {
            startVisualizer()
        } else {
            Toast.makeText(this, "マイクなしでは反応できません", Toast.LENGTH_LONG).show()
        }
    }

    override fun onResume() {
        super.onResume()
        hideSystemUi()
        if (renderer != null) {
            glView.onResume()
            if (hasMicPermission()) mic.start()
        }
    }

    override fun onPause() {
        if (renderer != null) glView.onPause()
        mic.stop()
        super.onPause()
    }

    override fun onDestroy() {
        mic.stop()
        super.onDestroy()
    }

    private fun hideSystemUi() {
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
    }

    companion object {
        private const val REQ_MIC = 1001
    }
}
