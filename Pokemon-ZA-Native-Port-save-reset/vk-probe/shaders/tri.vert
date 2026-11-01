#version 450
// ZA Vulkan probe: one triangle centred on the screen, rotated by a push constant;
// white while a controller button is held (push.white = 1).
layout(push_constant) uniform Push { float angle; float aspect; float white; } push;
layout(location = 0) out vec3 colour;
void main() {
    const vec2 corners[3] = vec2[3](vec2(0.0, -0.6), vec2(0.52, 0.3), vec2(-0.52, 0.3));
    const vec3 colours[3] = vec3[3](vec3(1.0, 0.0, 0.0), vec3(0.0, 1.0, 0.0), vec3(0.0, 0.0, 1.0));
    vec2 v = corners[gl_VertexIndex];
    float s = sin(push.angle);
    float c = cos(push.angle);
    vec2 r = vec2(v.x * c - v.y * s, v.x * s + v.y * c);
    gl_Position = vec4(r.x / push.aspect, r.y, 0.0, 1.0);
    colour = mix(colours[gl_VertexIndex], vec3(1.0), push.white);
}
