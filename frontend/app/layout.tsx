import './globals.css'
import {ReactNode} from 'react'

export const metadata = {
    title: 'Каталог',
}

export default function RootLayout({ children }: { children: ReactNode }) {
    return (
        <html>
            <body>
                {children}
            </body>
        </html>
    )
}