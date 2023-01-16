from math import *  # pylint: disable=unused-wildcard-import
import adsk.core  # pylint: disable=import-error
import adsk.fusion  # pylint: disable=import-error
import adsk.cam  # pylint: disable=import-error
import traceback

# needed for events
handlers = []

###############################################################################
###############################################################################
###############################################################################

# class used to create equation driven surface


class equation_driven_surface():
    def __init__(self, eds_input):
        app = adsk.core.Application.get()
        self.root_comp = app.activeProduct.rootComponent
        self.sketches = self.root_comp.sketches
        self.timeline = app.activeProduct.timeline
        # get inputs
        self.equation = eds_input[0]
        self.domain = eds_input[1]
        self.has_base = eds_input[2]
        self.base_type = eds_input[3]
        self.base_offset = eds_input[4]
        self.res_type = eds_input[5]
        self.step_size = eds_input[6]
        self.num_interv_x = eds_input[7]
        self.num_interv_y = eds_input[8]
        self.plane = eds_input[9]
        # internal variables
        self.points = []  # array of points of form [[p1,p2],[p4,p5]]
        self.loft_sections = []
        self.rails = []
        self.min_z = 0
        self.base_level = 0

    ##########################################################################

    def make_xy_points_grid(self):
        """
        creates a 2D array of points in the xy-plane in the specifed domain
        uses step size, number of intervals (x & y) and resolution type
        """
        x_min, x_max = self.domain[0][0], self.domain[0][1]
        y_min, y_max = self.domain[1][0], self.domain[1][1]
        # these two different methods reflect the difference in input type: step size vs number of intervals
        if self.res_type == "Interval Length":
            x_step = y_step = self.step_size
            row = []
            x = x_min
            while x <= x_max:
                y = y_min
                while y <= y_max:
                    row.append([x, y])
                    y += y_step
                x += x_step
                self.points.append(row)
                row = []
        else:
            row = []
            for i in range(0, self.num_interv_x+1):
                for j in range(0, self.num_interv_y+1):
                    x = (i/self.num_interv_x)*(x_max-x_min)+x_min
                    y = (j/self.num_interv_y)*(y_max-y_min)+y_min
                    row.append([x, y])
                self.points.append(row)
                row = []
        return

    def add_z_dimension(self):
        """
        takes a set of points in the xy-plane and a function_string and returns
        a set of points in 3D space as well as the minimum z value
        """
        def z_function(x, y):
            return eval(self.equation)
        self.min_z = z_function(self.points[0][0][0],
                                self.points[0][0][1])  # initialize
        for row in self.points:
            for point in row:
                point.append(z_function(point[0], point[1]))
                if point[2] < self.min_z:
                    self.min_z = point[2]
        return self.points

    def center_points(self):
        """
        shift all points such that they are in the center of the xy-plane
        """
        points = self.points
        shifted_points = points
        x_min, x_max = points[0][0][0], points[-1][0][0]
        y_min, y_max = points[0][0][1], points[0][-1][1]
        x_offset = (x_min + x_max) / 2
        y_offset = (y_min + y_max) / 2
        print(y_offset)
        for i in range(len(points)):
            for j in range(len(points[i])):
                x = points[i][j][0] - x_offset
                y = points[i][j][1] - y_offset
                z = points[i][j][2]
                shifted_points[i][j] = [x, y, z]
        return shifted_points

    # interprets the base_type set by the user and returns a base_level
    def get_base_level(self):
        if self.base_type == "Automatic":
            if self.min_z < -self.base_offset:
                self.base_level = self.min_z + self.base_offset
            else:
                self.base_level = 0
        elif self.base_type == "xy-plane":
            self.base_level = self.base_offset
        elif self.base_type == "Minimum Value":
            self.base_level = self.min_z + self.base_offset
        return

    # takes a set of points in 3D space and adds a set of points at base_level
    def add_base_points(self):
        for row in self.points:
            first_point = row[0]
            last_point = row[len(row) - 1]
            row.append([last_point[0], last_point[1], self.base_level])
            row.append([first_point[0], first_point[1], self.base_level])
        return self.points

    # returns the array of points outlining the solid body to be created
    def calculate_points(self):  # noqa
        self.make_xy_points_grid()
        points = self.add_z_dimension()
        points = self.center_points()
        if self.has_base:
            self.get_base_level()
            points = self.add_base_points()
        self.points = points
        return self.points

    ###########################################################################

    # plots the set of points
    def plot_points(self):
        sketch = self.sketches.add(self.plane)
        sketchPoints = sketch.sketchPoints
        for row in self.points:
            for point in row:
                x = point[0]
                y = point[1]
                z = point[2]
                point = adsk.core.Point3D.create(x, y, z)
                sketchPoints.add(point)

    # creates a line from cart_point1 to cart_point2. returns line object
    # inputs are of the form cart_point = [x,y,z]
    def make_line(self, sketch, cart_point1, cart_point2):
        Point3D = adsk.core.Point3D
        point1 = Point3D.create(cart_point1[0], cart_point1[1], cart_point1[2])
        point2 = Point3D.create(cart_point2[0], cart_point2[1], cart_point2[2])
        line = sketch.sketchCurves.sketchLines.addByTwoPoints(point1, point2)
        return line

    # creates multiple lines based on a set of ordered points that are ideally
    # in the same plane
    def make_section(self, points_2D, type):
        sketch = self.sketches.add(self.plane)  # create sketch object
        sketch.isLightBulbOn = False  # hide sketches no matter what
        lines_collection = adsk.core.ObjectCollection.create()  # for path
        for i in range(len(points_2D) - 1):
            line = self.make_line(sketch, points_2D[i], points_2D[i + 1])
            lines_collection.add(line)
        if type == 'profile':
            self.make_line(sketch, points_2D[len(points_2D) - 1], points_2D[0])
            profile = sketch.profiles.item(0)
            return profile
        elif type == 'polyline':
            return sketch.sketchCurves
        elif type == 'path':
            path = self.root_comp.features.createPath(lines_collection)
            return path

    # creates multiple sections of desired type
    def make_sections(self, points, type):
        sections = []
        for i in range(len(points)):
            sections.append(self.make_section(
                points[i], type))
        return sections

    # like above but specifically for lofting (not rails)
    def make_loft_sections(self):
        if self.has_base:
            type = 'profile'
        else:
            type = 'path'
        self.loft_sections = self.make_sections(
            self.points, type)
        return

    # transposes arrays
    def transpose_array(self, array):
        col = []
        transposed_array = []
        for i in range(len(array[0])):
            for j in range(len(array)):
                col.append(array[j][i])
            transposed_array.append(col)
            col = []
        return transposed_array

    # makes rails for loft
    def make_rails(self):
        tpd_points = self.transpose_array(self.points)
        tpd_rails = self.make_sections(
            tpd_points, 'polyline')
        self.rails = self.transpose_array(tpd_rails)
        return

    # to stich surfaces together at end of surface loft
    def stitch_surfaces(self, surfaces):
        stitch_features = self.root_comp.features.stitchFeatures
        tolerance = adsk.core.ValueInput.createByReal(1.0)  # random tolerance
        stitch_input = stitch_features.createInput(surfaces, tolerance)
        stitch_features.add(stitch_input)
        return

    def loft_single(self, section_pair, loft_rails):
        join_feature = adsk.fusion.FeatureOperations.JoinFeatureOperation
        loft_features = self.root_comp.features.loftFeatures
        loft_input = loft_features.createInput(join_feature)
        for rail in loft_rails:
            loft_input.centerLineOrRails.addRail(rail)
        for section in section_pair:
            loft_input.loftSections.add(section)
        loft_feature = loft_features.add(loft_input)
        return loft_feature

    def loft_multiple(self):
        sections = self.loft_sections
        rails = self.rails  # so we don't make these backwards
        sections.reverse()
        rails.reverse()  # makes the normals look better when without base
        surfaces = adsk.core.ObjectCollection.create()
        for i in range(len(sections) - 1):
            loft_rails = rails[i]
            section_pair = [sections[i], sections[i + 1]]
            loft_feature = self.loft_single(
                section_pair, loft_rails)
            surface = loft_feature.bodies.item(0)
            if not self.has_base:
                surfaces.add(surface)
        if not self.has_base and len(surfaces) > 1:
            self.stitch_surfaces(surfaces)  # to connect all the surfaces
        return

    ###########################################################################

    # groups timeline items into three groups
    def group_timeline_objects(self):
        # there are are lot of whacky edge cases here
        timeline_groups = self.timeline.timelineGroups
        if not self.has_base:
            names = ['Loft & Stitch', 'Rails', 'Loft Paths']
            lengths = [len(self.loft_sections),
                       len(self.rails[0]),
                       len(self.loft_sections)]
        else:
            names = ['Loft', 'Rails', 'Loft Profiles']
            lengths = [len(self.loft_sections) - 1,
                       len(self.rails[0]),
                       len(self.loft_sections)]
        start_index = self.timeline.count

        if len(self.loft_sections) <= 2:  # in the situation where only one loft is required
            names.pop(0)
            lengths.pop(0)
            start_index -= 1
        for length, name in zip(lengths, names):
            end_index = start_index - 1
            start_index = end_index - length + 1
            timeline_groups.add(start_index, end_index).name = name
        return


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Get the CommandDefinitions collection.
        cmdDefs = ui.commandDefinitions

        # Create a command definition and add a button to the CREATE panel.
        cmdDef = cmdDefs.addButtonDefinition(
            'eds_id',
            'Equation Driven Surface',
            'Creates a surface modelled by an equation of the form\nz = f(x,y)',
            'resources/toolbar_icons')
        cmdDef.toolClipFilename = "resources/tool_clip_2.png"
        createPanel = ui.allToolbarPanels.itemById('SurfaceCreatePanel')
        createPanel.controls.addCommand(cmdDef)

        # Connect to the command created event.
        onCommandCreated = CommandCreatedEventHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        handlers.append(onCommandCreated)

        if context['IsApplicationStartup'] is False:
            ui.messageBox(
                'The "Equation Driven Surface" command has been added\nto the CREATE panel of the SURFACE workspace.')
    except:  # noqa
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        createPanel = ui.allToolbarPanels.itemById('SurfaceCreatePanel')
        eds_button = createPanel.controls.itemById('eds_id')
        if eds_button:
            eds_button.deleteMe()

        cmdDef = ui.commandDefinitions.itemById('eds_id')
        if cmdDef:
            cmdDef.deleteMe()
    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


# Create
class CommandCreatedEventHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface  # noqa

            # Default settings
            default_equation = "cos((2/3)*pow((pow(x,2)+pow(y,2)),(1/2)))+1"
            default_x_min = adsk.core.ValueInput.createByReal(-4)
            default_x_max = adsk.core.ValueInput.createByReal(4)
            default_y_min = adsk.core.ValueInput.createByReal(-4)
            default_y_max = adsk.core.ValueInput.createByReal(4)
            default_step_size = 1
            default_interval_num = 10
            default_base_offset = adsk.core.ValueInput.createByReal(-1)

            # Get command inputs
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            cmd = eventArgs.command
            inputs = cmd.commandInputs

            # Command Inputs
            # Section 1: Image & Equation
            inputs.addImageCommandInput(
                'image_id', '', "resources/sample_plot.png")
            inputs.addTextBoxCommandInput(
                'intro', '', '<div align="center">This add-in plots the surface specified by the equation below</div>', 3, True)
            inputs.addTextBoxCommandInput(
                'equation', 'z = f(x,y) = ', default_equation, 3, False)
            inputs.itemById(
                'equation').tooltip = "Define the function being plotted"

            # Setion 2: Domain
            domain_inputs = inputs.addGroupCommandInput('domain_id', 'Domain')
            domain_inputs.isExpanded = True
            domain_child = domain_inputs.children
            domain_child.addValueInput(
                'x_min_id', 'X Minimum', '', default_x_min)
            domain_child.addValueInput(
                'x_max_id', 'X Maximum', '', default_x_max)
            domain_child.addValueInput(
                'y_min_id', 'Y Minimum', '', default_y_min)
            domain_child.addValueInput(
                'y_max_id', 'Y Maximum', '', default_y_max)

            # Section 3: Resolution
            resolution_inputs = inputs.addGroupCommandInput(
                'resolution_id', 'Resolution')
            resolution_inputs.isExpanded = True
            res_child = resolution_inputs.children
            res_dropdown_input = res_child.addDropDownCommandInput(
                'res_type', 'Define using', adsk.core.DropDownStyles.LabeledIconDropDownStyle)
            inputs.itemById(
                'res_type').tooltip = "Chose how the resolution is defined"
            res_dropdown_items = res_dropdown_input.listItems
            res_dropdown_items.add("Interval Length", True)
            res_dropdown_items.add("Number of Intervals", False)
            res_child.addFloatSpinnerCommandInput(
                'step_size', 'Step Size', '', 0.01, 10, 0.25, default_step_size)
            res_child.addIntegerSpinnerCommandInput(
                'num_interv_x', 'Num Intervals X', 1, 1000, 1, default_interval_num)
            res_child.addIntegerSpinnerCommandInput(
                'num_interv_y', 'Num Intervals Y', 1, 1000, 1, default_interval_num)
            # initialize as hidden
            inputs.itemById('num_interv_y').isVisible = False
            inputs.itemById('num_interv_x').isVisible = False

            # Section 4: Base
            base_inputs = inputs.addGroupCommandInput('base_id', 'Solid Body')
            base_inputs.isEnabledCheckBoxDisplayed = True
            base_inputs.isEnabledCheckBoxChecked = False
            base_child = base_inputs.children
            base_child.addTextBoxCommandInput(
                'intro', '', 'Define base level:', 1, True)
            base_dropdown_input = base_child.addDropDownCommandInput(
                'base_dropdown_id', 'Relative to', adsk.core.DropDownStyles.LabeledIconDropDownStyle)
            inputs.itemById(
                'base_dropdown_id').tooltip = "Chose how the base level is defined"
            base_dropdown_items = base_dropdown_input.listItems
            base_dropdown_items.add("Automatic", True)
            base_dropdown_items.add("xy-plane", False)
            base_dropdown_items.add("Minimum Value", False)
            base_child.addValueInput(
                'base_offset_id', 'Offset', '', default_base_offset)
            inputs.itemById(
                'base_offset_id').tooltip = "Offset of the base from the xy-plane or the plot's minimum value"

            # tooltip descriptions
            inputs.itemById(
                'base_dropdown_id').tooltipDescription = "The base level is set relative to some geometry with an Offset\
                specified below<br><br>\
                \
                <b>Automatic</b> - sets the base level to Z = 0 if the lowest \
                value the function plus Offset is above the xy-plane. Otherwise \
                the base level is set to the function minimum plus the offset. \
                Effectively this means that the base level is set to zero \
                whenever possible while avoiding loft errors. <br><br> \
                \
                <b>xy-plane</b> - in this mode the base level is set to the \
                Offset value directly. This may cause issues if the base level \
                chosen intersects the plotted points.<br><br>\
                \
                <b>Minimum Value</b> - The base level is set relative to the \
                minimum value the function takes on in the domain specified.\
                "
            inputs.itemById(
                'step_size').tooltipDescription = "It is best if x and y domains are multiples of the step size"
            inputs.itemById('equation').tooltipDescription = "Some other expressions to try:<br>\
                x**2+y**2 Quadratic<br> \
                (exp(x)-exp(y))/10 Exponential<br>\
                sin(x+y)-cos(x) Sinusoidal<br>\
                sqrt(40-x**2-y**2) Hemisphere<br>\
                sqrt(x**2+y**2) Cone"

            # Connect to the execute event.
            onExecute = CommandExecuteHandler()
            cmd.execute.add(onExecute)
            handlers.append(onExecute)

            # Connect to the execute preview event
            onPreview = CommandExecutePreviewHandler()
            cmd.executePreview.add(onPreview)
            handlers.append(onPreview)

            # Connect to the validate inputs event
            onValidate = CommandValidateInputsHandler()
            cmd.validateInputs.add(onValidate)
            handlers.append(onValidate)

            # Connect to the input changed event
            onInputChanged = CommandInputChangedHandler()
            cmd.inputChanged.add(onInputChanged)
            handlers.append(onInputChanged)
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


# Execute
class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface

            # get command inputs
            event_args = adsk.core.CommandEventArgs.cast(args)
            inputs = event_args.command.commandInputs

            # read command inputs
            # Equation & Domain
            equation = inputs.itemById('equation').text
            x_min = inputs.itemById('x_min_id').value
            x_max = inputs.itemById('x_max_id').value
            y_min = inputs.itemById('y_min_id').value
            y_max = inputs.itemById('y_max_id').value
            domain = [[x_min, x_max], [y_min, y_max]]

            # Resolution
            res_type = inputs.itemById('res_type').selectedItem.name
            step_size = inputs.itemById('step_size').value
            num_interv_x = inputs.itemById('num_interv_x').value
            num_interv_y = inputs.itemById('num_interv_y').value

            # Base
            has_base = inputs.itemById('base_id').isEnabledCheckBoxChecked
            base_type = inputs.itemById('base_dropdown_id').selectedItem.name
            base_offset = inputs.itemById('base_offset_id').value

            # get xy_plane
            xy_plane = app.activeProduct.rootComponent.xYConstructionPlane

            # define equation driven surface input
            eds_input = [equation, domain, has_base, base_type,
                         base_offset, res_type, step_size, num_interv_x, num_interv_y, xy_plane]

            # make equation driven surface
            eds = equation_driven_surface(eds_input)
            try:
                eds.calculate_points()
                eds.make_loft_sections()
                eds.make_rails()
                eds.loft_multiple()
                eds.group_timeline_objects()
            except:
                ui.messageBox(
                    'There was some kind of error, please check the inputs and try again')

        except:  # noqa
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


# Preview
class CommandExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            event_args = adsk.core.CommandEventArgs.cast(args)
            inputs = event_args.command.commandInputs

            # Get command inputs
            # Equation & Domain
            equation = inputs.itemById('equation').text
            x_min = inputs.itemById('x_min_id').value
            x_max = inputs.itemById('x_max_id').value
            y_min = inputs.itemById('y_min_id').value
            y_max = inputs.itemById('y_max_id').value
            domain = [[x_min, x_max], [y_min, y_max]]

            # Base
            has_base = inputs.itemById('base_id').isEnabledCheckBoxChecked
            base_type = inputs.itemById('base_dropdown_id').selectedItem.name
            base_offset = inputs.itemById('base_offset_id').value

            # Resolution
            res_type = inputs.itemById('res_type').selectedItem.name
            step_size = inputs.itemById('step_size').value
            num_interv_x = inputs.itemById('num_interv_x').value
            num_interv_y = inputs.itemById('num_interv_y').value

            # validation
            max_verticies = 350
            if res_type == "Interval Length":
                total_vertices = (x_max-x_min)*(y_max-y_min)/step_size
            else:
                total_vertices = (num_interv_x+1)*(num_interv_y+1)
            if total_vertices > max_verticies:
                response = ui.messageBox(
                    'Resolutions this high may take a while to process. Do you wish to proceed anyway? (if not, resolution will be adjusted)', '', 3)
                if response == 3:  # if no
                    if res_type == "Interval Length":
                        step_size = (x_max-x_min)*(y_max-y_min)/max_verticies
                        inputs.itemById('step_size').value = step_size
                    else:
                        max_num_interv = round(sqrt(max_verticies))-2
                        inputs.itemById('num_interv_x').value = max_num_interv
                        inputs.itemById('num_interv_y').value = max_num_interv

            # get xy_plane
            app = adsk.core.Application.get()
            xy_plane = app.activeProduct.rootComponent.xYConstructionPlane

            # define equation driven surface input
            eds_input = [equation, domain, has_base, base_type,
                         base_offset, res_type, step_size, num_interv_x, num_interv_y, xy_plane]

            eds = equation_driven_surface(eds_input)
            eds.calculate_points()
            eds.plot_points()
        except:  # noqa
            pass  # try except to avoid crashing while inputs are being changed


# Validate
class CommandValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)
        inputs = eventArgs.firingEvent.sender.commandInputs

        # Check to see if the check box is checked or not.
        x_min = inputs.itemById('x_min_id').value
        x_max = inputs.itemById('x_max_id').value
        y_min = inputs.itemById('y_min_id').value
        y_max = inputs.itemById('y_max_id').value
        step_size = inputs.itemById('step_size').value
        res_type = inputs.itemById('res_type').selectedItem.name

        if res_type == 'Interval Length':
            if x_max - x_min < step_size or y_max - y_min < step_size:
                eventArgs.areInputsValid = False
            else:
                eventArgs.areInputsValid = True
        else:
            if x_max-x_min <= 0 or y_max-y_min <= 0:
                eventArgs.areInputsValid = False
            else:
                eventArgs.areInputsValid = True


# Update
class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        eventArgs = adsk.core.InputChangedEventArgs.cast(args)
        inputs = eventArgs.firingEvent.sender.commandInputs

        step_size_input = inputs.itemById('step_size')
        num_interv_y = inputs.itemById('num_interv_y')
        num_interv_x = inputs.itemById('num_interv_x')

        # Change the visibility of 'step size' and 'number of intervals' inputs
        changedInput = eventArgs.input
        if changedInput.id == 'res_type':
            if changedInput.selectedItem.name == 'Number of Intervals':
                num_interv_x.isVisible = True
                num_interv_y.isVisible = True
                step_size_input.isVisible = False
            else:
                num_interv_x.isVisible = False
                num_interv_y.isVisible = False
                step_size_input.isVisible = True
