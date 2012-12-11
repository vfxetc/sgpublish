from PyQt4 import QtGui


class ImportTabs(QtGui.QTabWidget):
    
    """Slight extension to the standard QTabWidget which does two things:
    
    1) Passes the `import_()` method on to the active tab.
    2) Resets its sizeHint whenever the tab is changed.
    
    """
    
    def __init__(self):
        super(ImportTabs, self).__init__()
        self._auto_adjust = True
        self._setup_ui()
    
    def _setup_ui(self):
        
        # Reset the background of the widgets to the window colour.
        self.setStyleSheet('''
            QTabWidget {
                background-color: palette(window);
            }
        ''')
        self.currentChanged.connect(self._on_currentChanged)
    
    def autoAdjust(self):
        return self._auto_adjust
    
    def setAutoAdjust(self, v):
        self._auto_adjust = bool(v)
    
    def _on_currentChanged(self):
        if self._auto_adjust:
            self.updateGeometry()
            p = self.parent()
            while p:
                p.adjustSize()
                p = p.parent()
    
    def sizeHint(self):
        
        if not self._auto_adjust:
            return super(Widget, self).sizeHint()
        
        bar = self.tabBar()
        widget = self.currentWidget()
        
        hint = widget.sizeHint()
        hint.setHeight(hint.height() + bar.sizeHint().height())
        
        for i in xrange(self.count()):
            hint.setWidth(max(hint.width(), self.widget(i).sizeHint().width()))
        
        return hint
    
    def minimumSizeHint(self):
        if not self._auto_adjust:
            return super(Widget, self).minimumSizeHint()
        return self.sizeHint()
    
    def setPath(self, path):
        last_satisfied = None
        for i in xrange(self.count()):
            if self.widget(i).setPath(path):
                last_satisfied = i
        if last_satisfied is not None:
            self.setCurrentIndex(last_satisfied)

    def import_(self, **kwargs):
        return self.currentWidget().import_(**kwargs)

