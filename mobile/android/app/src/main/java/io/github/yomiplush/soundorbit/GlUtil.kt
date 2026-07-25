package io.github.yomiplush.soundorbit

import android.content.Context
import android.opengl.GLES30
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer

object GlUtil {
    fun loadAsset(ctx: Context, path: String): String =
        ctx.assets.open(path).bufferedReader().use { it.readText() }

    fun compile(type: Int, src: String): Int {
        val sh = GLES30.glCreateShader(type)
        GLES30.glShaderSource(sh, src)
        GLES30.glCompileShader(sh)
        val ok = IntArray(1)
        GLES30.glGetShaderiv(sh, GLES30.GL_COMPILE_STATUS, ok, 0)
        if (ok[0] == 0) {
            val log = GLES30.glGetShaderInfoLog(sh)
            GLES30.glDeleteShader(sh)
            throw RuntimeException("Shader compile: $log\n---\n$src")
        }
        return sh
    }

    fun link(vs: Int, fs: Int): Int {
        val p = GLES30.glCreateProgram()
        GLES30.glAttachShader(p, vs)
        GLES30.glAttachShader(p, fs)
        GLES30.glLinkProgram(p)
        val ok = IntArray(1)
        GLES30.glGetProgramiv(p, GLES30.GL_LINK_STATUS, ok, 0)
        if (ok[0] == 0) {
            val log = GLES30.glGetProgramInfoLog(p)
            throw RuntimeException("Program link: $log")
        }
        return p
    }

    fun program(ctx: Context, vertAsset: String, fragAsset: String): Int {
        val vs = compile(GLES30.GL_VERTEX_SHADER, loadAsset(ctx, vertAsset))
        val fs = compile(GLES30.GL_FRAGMENT_SHADER, loadAsset(ctx, fragAsset))
        return link(vs, fs)
    }

    fun floatBuffer(data: FloatArray): FloatBuffer =
        ByteBuffer.allocateDirect(data.size * 4).order(ByteOrder.nativeOrder()).asFloatBuffer().also {
            it.put(data); it.position(0)
        }
}
