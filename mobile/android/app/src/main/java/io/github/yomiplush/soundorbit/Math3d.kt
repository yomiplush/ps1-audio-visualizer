package io.github.yomiplush.soundorbit

import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.tan
import kotlin.math.sqrt

object Math3d {
    fun perspective(fovyDeg: Float, aspect: Float, zNear: Float, zFar: Float): FloatArray {
        val f = 1f / tan(Math.toRadians(fovyDeg.toDouble() / 2.0)).toFloat()
        val m = FloatArray(16)
        m[0] = f / maxOf(aspect, 1e-6f)
        m[5] = f
        m[10] = (zFar + zNear) / (zNear - zFar)
        m[11] = -1f
        m[14] = (2f * zFar * zNear) / (zNear - zFar)
        return m
    }

    fun lookAt(ex: Float, ey: Float, ez: Float, tx: Float, ty: Float, tz: Float): FloatArray {
        var fx = tx - ex; var fy = ty - ey; var fz = tz - ez
        val fl = sqrt(fx*fx+fy*fy+fz*fz) + 1e-9f
        fx /= fl; fy /= fl; fz /= fl
        // up = 0,1,0
        var sx = fy*0f - fz*1f; var sy = fz*0f - fx*0f; var sz = fx*1f - fy*0f
        val sl = sqrt(sx*sx+sy*sy+sz*sz) + 1e-9f
        sx /= sl; sy /= sl; sz /= sl
        val ux = sy*fz - sz*fy; val uy = sz*fx - sx*fz; val uz = sx*fy - sy*fx
        val m = FloatArray(16)
        // column-major OpenGL
        m[0]=sx; m[4]=sy; m[8]=sz; m[12]=-(sx*ex+sy*ey+sz*ez)
        m[1]=ux; m[5]=uy; m[9]=uz; m[13]=-(ux*ex+uy*ey+uz*ez)
        m[2]=-fx; m[6]=-fy; m[10]=-fz; m[14]=fx*ex+fy*ey+fz*ez
        m[3]=0f; m[7]=0f; m[11]=0f; m[15]=1f
        return m
    }

    fun mul(a: FloatArray, b: FloatArray): FloatArray {
        val r = FloatArray(16)
        for (c in 0 until 4) for (row in 0 until 4) {
            r[c*4+row] = a[0*4+row]*b[c*4+0] + a[1*4+row]*b[c*4+1] + a[2*4+row]*b[c*4+2] + a[3*4+row]*b[c*4+3]
        }
        return r
    }
}
