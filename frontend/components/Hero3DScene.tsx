"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

type SceneObjects = {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  group: THREE.Group;
  fans: THREE.Mesh[];
  frameId: number | null;
};

export function Hero3DScene() {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const objectsRef = useRef<SceneObjects | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;

    try {
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
      camera.position.set(4, 3.2, 6.2);
      camera.lookAt(0, 0.3, 0);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
      host.appendChild(renderer.domElement);

      const group = new THREE.Group();
      scene.add(group);

      const teal = new THREE.Color("#2dd4bf");
      const magenta = new THREE.Color("#d946ef");
      const darkPanel = new THREE.Color("#172033");
      const line = new THREE.Color("#526179");

      scene.add(new THREE.AmbientLight(0xffffff, 1.25));
      const key = new THREE.PointLight(teal, 48, 14);
      key.position.set(-3, 4, 4);
      scene.add(key);
      const rim = new THREE.PointLight(magenta, 28, 12);
      rim.position.set(3, -1, 3);
      scene.add(rim);

      const caseShell = new THREE.Mesh(
        new THREE.BoxGeometry(3.2, 3.5, 2.2),
        new THREE.MeshPhysicalMaterial({
          color: 0x223047,
          transparent: true,
          opacity: 0.16,
          roughness: 0.32,
          metalness: 0.2,
          transmission: 0.2
        })
      );
      group.add(caseShell);

      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(3.22, 3.52, 2.22)),
        new THREE.LineBasicMaterial({ color: line, transparent: true, opacity: 0.55 })
      );
      group.add(edges);

      const motherboard = new THREE.Mesh(
        new THREE.BoxGeometry(1.7, 2.35, 0.08),
        new THREE.MeshStandardMaterial({ color: darkPanel, roughness: 0.5, metalness: 0.15 })
      );
      motherboard.position.set(-0.35, 0.2, 0.54);
      group.add(motherboard);

      const cpu = new THREE.Mesh(
        new THREE.BoxGeometry(0.52, 0.52, 0.12),
        new THREE.MeshStandardMaterial({ color: 0x9ca8bd, roughness: 0.4, metalness: 0.6 })
      );
      cpu.position.set(-0.42, 0.55, 0.66);
      group.add(cpu);

      const gpu = new THREE.Mesh(
        new THREE.BoxGeometry(1.95, 0.42, 0.36),
        new THREE.MeshStandardMaterial({ color: 0x101827, roughness: 0.45, metalness: 0.35 })
      );
      gpu.position.set(0.08, -0.55, 0.85);
      group.add(gpu);

      const fanMaterial = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.4, metalness: 0.2 });
      const fanAccent = new THREE.MeshBasicMaterial({ color: teal, transparent: true, opacity: 0.9 });
      const fans: THREE.Mesh[] = [];
      [-0.42, 0.48].forEach((x) => {
        const fan = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.025, 8, 28), fanMaterial);
        fan.position.set(x, -0.55, 1.04);
        fan.rotation.x = Math.PI / 2;
        group.add(fan);
        fans.push(fan);
        const blade = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.025, 0.025), fanAccent);
        blade.position.copy(fan.position);
        blade.rotation.z = Math.PI / 5;
        group.add(blade);
        fans.push(blade);
      });

      [-0.86, -0.66].forEach((x) => {
        const ram = new THREE.Mesh(
          new THREE.BoxGeometry(0.08, 1.32, 0.13),
          new THREE.MeshStandardMaterial({ color: teal, emissive: teal, emissiveIntensity: 0.25 })
        );
        ram.position.set(x, 0.15, 0.72);
        group.add(ram);
      });

      const cooler = new THREE.Mesh(
        new THREE.TorusGeometry(0.33, 0.045, 10, 36),
        new THREE.MeshStandardMaterial({ color: magenta, emissive: magenta, emissiveIntensity: 0.22 })
      );
      cooler.position.set(-0.42, 0.55, 0.82);
      cooler.rotation.x = Math.PI / 2;
      group.add(cooler);
      fans.push(cooler);

      const psu = new THREE.Mesh(
        new THREE.BoxGeometry(1.25, 0.48, 0.72),
        new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.55, metalness: 0.2 })
      );
      psu.position.set(-0.55, -1.33, 0.42);
      group.add(psu);

      const resize = () => {
        if (!host || disposed) return;
        const width = host.clientWidth || 520;
        const height = host.clientHeight || 420;
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      };

      const animate = () => {
        if (disposed) return;
        if (!document.hidden) {
          const now = performance.now() * 0.001;
          group.rotation.y = Math.sin(now * 0.45) * 0.17 - 0.25;
          group.rotation.x = Math.sin(now * 0.32) * 0.05;
          group.position.y = Math.sin(now * 0.7) * 0.08;
          fans.forEach((fan, index) => {
            fan.rotation.z += index % 2 === 0 ? 0.05 : -0.04;
          });
          renderer.render(scene, camera);
        }
        objectsRef.current!.frameId = requestAnimationFrame(animate);
      };

      objectsRef.current = { scene, camera, renderer, group, fans, frameId: null };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(host);
      animate();

      return () => {
        disposed = true;
        observer.disconnect();
        const objects = objectsRef.current;
        if (objects?.frameId) cancelAnimationFrame(objects.frameId);
        scene.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            object.geometry.dispose();
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach((material) => material.dispose());
          }
        });
        renderer.dispose();
        renderer.domElement.remove();
        objectsRef.current = null;
      };
    } catch {
      setFailed(true);
    }
  }, []);

  return (
    <div ref={hostRef} className="relative h-[330px] w-full overflow-hidden rounded-lg border border-line bg-[#080d18] sm:h-[430px]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_35%,rgba(45,212,191,0.20),transparent_34%),radial-gradient(circle_at_68%_70%,rgba(217,70,239,0.18),transparent_30%)]" />
      {failed ? (
        <div className="absolute inset-0 grid place-items-center px-6 text-center text-sm leading-6 text-muted">
          3D preview unavailable on this device. The build wizard still works normally.
        </div>
      ) : null}
    </div>
  );
}
