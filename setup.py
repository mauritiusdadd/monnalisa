"""
${LICENSE_HEADER}
"""
import setuptools

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()

setuptools.setup(
    name="monnalisa",
    version="${PROGRAM_VERSION}",
    author="Maurizio D'Addona",
    author_email="mauritiusdadd@gmail.com",
    description="An interface to control Da Vinci printers",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="<private>",
    packages=setuptools.find_packages(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'PyQt5',
        'pyserial',
        'pycryptodome'
    ],
    extras_require={
        'Webcam interface for server': 'cv2',
    }, 
    entry_points={
        'console_scripts': [
            'monnalisa-server=monnalisa.server:main'
        ],
        'gui_scripts': [
            'monnalisa=monnalisa.xyzgui:main'
        ],
    },
    zip_safe=False,
    include_package_data=True
)
