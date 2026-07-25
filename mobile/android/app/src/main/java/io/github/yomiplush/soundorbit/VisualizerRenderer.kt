package io.github.yomiplush.soundorbit

import android.content.Context
import android.opengl.GLES30
import android.opengl.GLSurfaceView
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Mobile-tuned PS1 CRT visualizer (OpenGL ES 3.0).
 * Low internal res, trail, CRT post, spectrum bars — mic driven.
 */
class VisualizerRenderer(
    private val context: Context,
    private val mic: MicCapture,
) : GLSurfaceView.Renderer {

    // PS1 internal resolution (mobile ECO)
    private val internalW = 200
    private val internalH = 150
    private val bands = AudioAnalysis.BANDS

    private var progBg = 0
    private var progBar = 0
    private var progPost = 0
    private var progTrail = 0

    private var quadVbo = 0
    private var barVbo = 0
    private var barInstanceVbo = 0
    private var barVao = 0
    private var quadVao = 0

    private var fboScene = 0
    private var texScene = 0
    private var rboDepth = 0
    private var fboTrail = intArrayOf(0, 0)
    private var texTrail = intArrayOf(0, 0)
    private var trailIdx = 0

    private var viewW = 1
    private var viewH = 1
    private var t0 = System.nanoTime()
    private var frameI = 0
    private val lockedFps = 20f
    private val fixedDt = 1f / lockedFps

    private var angle = 0f
    private val spectrum = FloatArray(bands)
    private val instances = FloatArray(bands * 4)
    private val barVerts: FloatArray
    private val barVertexCount: Int

    init {
        // unit box (pos+normal), thin x/z
        val faces = arrayOf(
            floatArrayOf(-0.5f,0.5f,-0.5f, 0.5f,0.5f,-0.5f, 0.5f,0.5f,0.5f, -0.5f,0.5f,0.5f, 0f,1f,0f),
            floatArrayOf(-0.5f,-0.5f,0.5f, 0.5f,-0.5f,0.5f, 0.5f,-0.5f,-0.5f, -0.5f,-0.5f,-0.5f, 0f,-1f,0f),
            floatArrayOf(-0.5f,-0.5f,0.5f, -0.5f,0.5f,0.5f, 0.5f,0.5f,0.5f, 0.5f,-0.5f,0.5f, 0f,0f,1f),
            floatArrayOf(0.5f,-0.5f,-0.5f, 0.5f,0.5f,-0.5f, -0.5f,0.5f,-0.5f, -0.5f,-0.5f,-0.5f, 0f,0f,-1f),
            floatArrayOf(0.5f,-0.5f,0.5f, 0.5f,0.5f,0.5f, 0.5f,0.5f,-0.5f, 0.5f,-0.5f,-0.5f, 1f,0f,0f),
            floatArrayOf(-0.5f,-0.5f,-0.5f, -0.5f,0.5f,-0.5f, -0.5f,0.5f,0.5f, -0.5f,-0.5f,0.5f, -1f,0f,0f),
        )
        val list = ArrayList<Float>()
        for (f in faces) {
            val n = floatArrayOf(f[12], f[13], f[14])
            val idx = intArrayOf(0,1,2, 0,2,3)
            for (ii in idx) {
                val o = ii * 3
                list.add(f[o] * 0.22f); list.add(f[o+1]); list.add(f[o+2] * 0.22f)
                list.add(n[0]); list.add(n[1]); list.add(n[2])
            }
        }
        barVerts = list.toFloatArray()
        barVertexCount = barVerts.size / 6
        val radius = 3.2f
        for (i in 0 until bands) {
            val ang = (i / bands.toFloat()) * (Math.PI * 2).toFloat() - (Math.PI * 0.5).toFloat()
            instances[i*4] = cos(ang) * radius
            instances[i*4+1] = sin(ang) * radius
            instances[i*4+2] = 0.05f
            instances[i*4+3] = i.toFloat()
        }
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        progBg = GlUtil.program(context, "shaders/bg.vert", "shaders/bg.frag")
        progBar = GlUtil.program(context, "shaders/bar.vert", "shaders/bar.frag")
        progPost = GlUtil.program(context, "shaders/post.vert", "shaders/post.frag")
        progTrail = GlUtil.program(context, "shaders/post.vert", "shaders/trail.frag")

        val quad = floatArrayOf(-1f,-1f, 1f,-1f, -1f,1f, 1f,1f)
        val qBuf = GlUtil.floatBuffer(quad)
        val vaos = IntArray(2)
        GLES30.glGenVertexArrays(2, vaos, 0)
        quadVao = vaos[0]; barVao = vaos[1]
        val vbos = IntArray(3)
        GLES30.glGenBuffers(3, vbos, 0)
        quadVbo = vbos[0]; barVbo = vbos[1]; barInstanceVbo = vbos[2]

        GLES30.glBindVertexArray(quadVao)
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, quadVbo)
        GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER, quad.size * 4, qBuf, GLES30.GL_STATIC_DRAW)
        GLES30.glEnableVertexAttribArray(0)
        GLES30.glVertexAttribPointer(0, 2, GLES30.GL_FLOAT, false, 8, 0)

        val bBuf = GlUtil.floatBuffer(barVerts)
        GLES30.glBindVertexArray(barVao)
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, barVbo)
        GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER, barVerts.size * 4, bBuf, GLES30.GL_STATIC_DRAW)
        GLES30.glEnableVertexAttribArray(0)
        GLES30.glVertexAttribPointer(0, 3, GLES30.GL_FLOAT, false, 24, 0)
        GLES30.glEnableVertexAttribArray(1)
        GLES30.glVertexAttribPointer(1, 3, GLES30.GL_FLOAT, false, 24, 12)
        val iBuf = GlUtil.floatBuffer(instances)
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, barInstanceVbo)
        GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER, instances.size * 4, iBuf, GLES30.GL_DYNAMIC_DRAW)
        GLES30.glEnableVertexAttribArray(2)
        GLES30.glVertexAttribPointer(2, 4, GLES30.GL_FLOAT, false, 16, 0)
        GLES30.glVertexAttribDivisor(2, 1)

        GLES30.glBindVertexArray(0)
        GLES30.glEnable(GLES30.GL_DEPTH_TEST)
        GLES30.glEnable(GLES30.GL_BLEND)
        GLES30.glBlendFunc(GLES30.GL_SRC_ALPHA, GLES30.GL_ONE_MINUS_SRC_ALPHA)

        allocTargets()
        t0 = System.nanoTime()
    }

    private fun allocTargets() {
        deleteTargets()
        texScene = genTex(internalW, internalH)
        rboDepth = genRbo(internalW, internalH)
        fboScene = genFbo(texScene, rboDepth)
        for (i in 0..1) {
            texTrail[i] = genTex(internalW, internalH)
            fboTrail[i] = genFboColorOnly(texTrail[i])
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, fboTrail[i])
            GLES30.glClearColor(0f,0f,0f,1f)
            GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT)
        }
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
        trailIdx = 0
    }

    private fun genTex(w: Int, h: Int): Int {
        val t = IntArray(1)
        GLES30.glGenTextures(1, t, 0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, t[0])
        GLES30.glTexImage2D(GLES30.GL_TEXTURE_2D, 0, GLES30.GL_RGBA, w, h, 0, GLES30.GL_RGBA, GLES30.GL_UNSIGNED_BYTE, null)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_NEAREST)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_NEAREST)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_CLAMP_TO_EDGE)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE)
        return t[0]
    }

    private fun genRbo(w: Int, h: Int): Int {
        val r = IntArray(1)
        GLES30.glGenRenderbuffers(1, r, 0)
        GLES30.glBindRenderbuffer(GLES30.GL_RENDERBUFFER, r[0])
        GLES30.glRenderbufferStorage(GLES30.GL_RENDERBUFFER, GLES30.GL_DEPTH_COMPONENT16, w, h)
        return r[0]
    }

    private fun genFbo(color: Int, depth: Int): Int {
        val f = IntArray(1)
        GLES30.glGenFramebuffers(1, f, 0)
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, f[0])
        GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER, GLES30.GL_COLOR_ATTACHMENT0, GLES30.GL_TEXTURE_2D, color, 0)
        GLES30.glFramebufferRenderbuffer(GLES30.GL_FRAMEBUFFER, GLES30.GL_DEPTH_ATTACHMENT, GLES30.GL_RENDERBUFFER, depth)
        return f[0]
    }

    private fun genFboColorOnly(color: Int): Int {
        val f = IntArray(1)
        GLES30.glGenFramebuffers(1, f, 0)
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, f[0])
        GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER, GLES30.GL_COLOR_ATTACHMENT0, GLES30.GL_TEXTURE_2D, color, 0)
        return f[0]
    }

    private fun deleteTargets() {
        if (fboScene != 0) GLES30.glDeleteFramebuffers(1, intArrayOf(fboScene), 0)
        if (texScene != 0) GLES30.glDeleteTextures(1, intArrayOf(texScene), 0)
        if (rboDepth != 0) GLES30.glDeleteRenderbuffers(1, intArrayOf(rboDepth), 0)
        for (i in 0..1) {
            if (fboTrail[i] != 0) GLES30.glDeleteFramebuffers(1, intArrayOf(fboTrail[i]), 0)
            if (texTrail[i] != 0) GLES30.glDeleteTextures(1, intArrayOf(texTrail[i]), 0)
            fboTrail[i] = 0; texTrail[i] = 0
        }
        fboScene = 0; texScene = 0; rboDepth = 0
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        viewW = max(1, width)
        viewH = max(1, height)
        GLES30.glViewport(0, 0, viewW, viewH)
    }

    override fun onDrawFrame(gl: GL10?) {
        val a = mic.snapshot()
        if (a.ready && a.spectrum.size == bands) {
            for (i in 0 until bands) {
                spectrum[i] = spectrum[i] * 0.35f + a.spectrum[i] * 0.65f
            }
        }
        val energy = (a.rms * 0.7f + a.bass * 0.5f + a.mid * 0.3f).coerceIn(0f, 1.5f)
        val beat = a.beat
        val dt = fixedDt
        angle += dt * (0.18f + energy * 0.35f + beat * 0.5f)
        val t = frameI * fixedDt
        frameI++

        for (i in 0 until bands) {
            var h = spectrum[i]
            h = h * h * 2.8f + h * 1.2f
            instances[i*4+2] = max(0.04f, min(4.5f, h * (0.9f + a.bass * 0.4f)))
        }

        // --- scene offscreen ---
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, fboScene)
        GLES30.glViewport(0, 0, internalW, internalH)
        GLES30.glClearColor(0.02f, 0.03f, 0.06f, 1f)
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)

        GLES30.glDisable(GLES30.GL_DEPTH_TEST)
        GLES30.glUseProgram(progBg)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBg, "uTime"), t)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBg, "uEnergy"), energy)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBg, "uBeat"), beat)
        GLES30.glBindVertexArray(quadVao)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)

        GLES30.glEnable(GLES30.GL_DEPTH_TEST)
        val aspect = internalW.toFloat() / internalH
        val proj = Math3d.perspective(52f, aspect, 0.1f, 80f)
        val camR = 9.5f - energy * 1.2f - beat * 0.8f
        val camH = 4.2f + a.mid * 0.8f
        val ex = cos(angle) * camR
        val ez = sin(angle) * camR
        val view = Math3d.lookAt(ex, camH, ez, 0f, 0.9f + a.bass * 0.4f, 0f)
        val vp = Math3d.mul(proj, view)

        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, barInstanceVbo)
        GLES30.glBufferSubData(GLES30.GL_ARRAY_BUFFER, 0, instances.size * 4, GlUtil.floatBuffer(instances))
        GLES30.glUseProgram(progBar)
        GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(progBar, "uMVP"), 1, false, vp, 0)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBar, "uTime"), t)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBar, "uBass"), a.bass)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBar, "uBands"), bands.toFloat())
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progBar, "uBeat"), beat)
        GLES30.glBindVertexArray(barVao)
        GLES30.glDrawArraysInstanced(GLES30.GL_TRIANGLES, 0, barVertexCount, bands)

        // trail
        val src = trailIdx
        val dst = 1 - trailIdx
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, fboTrail[dst])
        GLES30.glViewport(0, 0, internalW, internalH)
        GLES30.glDisable(GLES30.GL_DEPTH_TEST)
        GLES30.glUseProgram(progTrail)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progTrail, "uDecay"), 0.80f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progTrail, "uSceneGain"), 0.32f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progTrail, "uZoom"), 0.997f)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texScene)
        GLES30.glUniform1i(GLES30.glGetUniformLocation(progTrail, "uScene"), 0)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE1)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texTrail[src])
        GLES30.glUniform1i(GLES30.glGetUniformLocation(progTrail, "uPrev"), 1)
        GLES30.glBindVertexArray(quadVao)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)
        trailIdx = dst

        // CRT post to screen
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
        GLES30.glViewport(0, 0, viewW, viewH)
        GLES30.glClearColor(0f,0f,0f,1f)
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT)
        GLES30.glUseProgram(progPost)
        val trailMix = (0.36f + energy * 0.05f + beat * 0.05f).coerceIn(0.25f, 0.55f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uTrailMix"), trailMix)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uEnergy"), energy)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uBeat"), beat)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uTime"), t)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uExposure"), 0.90f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uBarrel"), 0.10f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uScanline"), 0.95f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(progPost, "uVignette"), 0.45f)
        GLES30.glUniform2f(GLES30.glGetUniformLocation(progPost, "uInternal"), internalW.toFloat(), internalH.toFloat())
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texScene)
        GLES30.glUniform1i(GLES30.glGetUniformLocation(progPost, "uScene"), 0)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE1)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texTrail[trailIdx])
        GLES30.glUniform1i(GLES30.glGetUniformLocation(progPost, "uTrail"), 1)
        GLES30.glBindVertexArray(quadVao)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)
    }
}
