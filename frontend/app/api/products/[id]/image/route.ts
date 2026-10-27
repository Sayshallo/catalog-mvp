import { NextRequest } from "next/server";

export const runtime = "nodejs";

export async function GET(
        request: NextRequest,
        context: { params: Promise<{ id: string}> }
) {
        try {

                const { id } = await context.params;

                if (!/^\d+$/.test(id)) {
                        return new Response("", {status: 400});
                }

                const backendUrl = process.env.API_URL;

                if (!backendUrl) {
                        console.error("Не задан API_URL");
                        return new Response("Сервис временно недоступен", {status: 503});
                }

                const response = await fetch(
                        `${backendUrl}/api/products/${id}/image`,
                        {
                                method: "GET",
                                cache: "no-store",
                        },
                );

                if (!response.ok) {
                        return new Response("Изображение не найдено", {status: response.status});
                }

                const content_type = response.headers.get("content-type") || "application/octet-stream";

                return new Response(response.body, {status: 200,
                        headers: {
                                "Content-Type": content_type,
                                "Cache-Control": "public, max-age=3600",
                                "X-Content-Type-Options": "nosniff",
                        }
                });
        } catch (error) {
                console.error("Ошибка при получении изображения. Текст ошибки:", error);

                return new Response("Не удалось получить изображение...", { status: 502 },);
                }
}
