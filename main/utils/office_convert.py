"""Isolated legacy Microsoft Office conversion helper.

Run as a subprocess so a corrupt document or a blocked Office dialog cannot
hold a Django worker indefinitely.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import contextlib


def convert(source: Path, destination: Path):
    import pythoncom
    import win32com.client

    extension = source.suffix.lower()
    pythoncom.CoInitialize()
    app = None
    document = None
    try:
        if extension == ".doc":
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            app.AutomationSecurity = 3
            document = app.Documents.Open(
                str(source.resolve()),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                NoEncodingDialog=True,
            )
            document.SaveAs2(str(destination.resolve()), FileFormat=16)
        elif extension == ".xls":
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            app.AutomationSecurity = 3
            app.AskToUpdateLinks = False
            document = app.Workbooks.Open(
                str(source.resolve()),
                UpdateLinks=0,
                ReadOnly=True,
                IgnoreReadOnlyRecommended=True,
            )
            document.SaveAs(str(destination.resolve()), FileFormat=51)
        elif extension == ".ppt":
            app = win32com.client.DispatchEx("PowerPoint.Application")
            app.AutomationSecurity = 3
            document = app.Presentations.Open(
                str(source.resolve()),
                ReadOnly=True,
                Untitled=False,
                WithWindow=False,
            )
            document.SaveAs(str(destination.resolve()), 24)
        else:
            raise ValueError(f"Unsupported legacy Office extension: {extension}")
    finally:
        with contextlib.suppress(Exception):
            document.Close() if extension == ".ppt" else document.Close(False)
        with contextlib.suppress(Exception):
            app.Quit()
        pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    convert(args.source, args.destination)


if __name__ == "__main__":
    main()
